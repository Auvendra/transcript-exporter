from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlsplit

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
)

class ExportError(Exception):
    pass


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
}

def extract_video_id(value: str) -> str:
    value = value.strip().strip('<>"\'')
    if VIDEO_ID.fullmatch(value):
        return value
    if not value or len(value) > 4096 or any(c.isspace() for c in value):
        raise ExportError("Paste one YouTube video link into the box above.")
    try:
        url = urlsplit(value if "://" in value else "https://" + value)
        if url.scheme not in {"http", "https"}:
            raise ValueError
        host = (url.hostname or "").lower()
        parts = url.path.strip("/").split("/")
        video_id = ""
        if host in {"youtu.be", "www.youtu.be"} and len(parts) == 1:
            video_id = parts[0]
        elif host in YOUTUBE_HOSTS:
            if parts == ["watch"]:
                video_id = parse_qs(url.query).get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live", "v"}:
                video_id = parts[1]
        if VIDEO_ID.fullmatch(video_id):
            return video_id
    except ValueError:
        pass
    raise ExportError("That isn't a valid YouTube video link. Try a watch, Shorts, or youtu.be link.")

@dataclass(frozen=True)
class Segment:
    text: str
    start: float
    duration: float


def timestamp(seconds: float) -> str:
    hours, remainder = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

@dataclass(frozen=True)
class TranscriptResult:
    video_id: str
    language: str
    language_code: str
    is_generated: bool
    segments: tuple[Segment, ...]

    def text(self, include_timestamps: bool = False) -> str:
        if include_timestamps:
            return "\n".join(f"[{timestamp(s.start)}] {s.text}" for s in self.segments)
        paragraphs, current = [], []
        word_count = 0
        previous_end = 0.0
        for segment in self.segments:
            if current and (segment.start - previous_end >= 2.0 or word_count >= 110):
                paragraphs.append(" ".join(current))
                current, word_count = [], 0
            current.append(segment.text)
            word_count += len(segment.text.split())
            previous_end = segment.start + segment.duration
        if current:
            paragraphs.append(" ".join(current))
        return "\n\n".join(paragraphs)

class TimeoutSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (6, 20))
        return super().request(method, url, **kwargs)

def fetch_transcript(video_id: str) -> TranscriptResult:
    try:
        with TimeoutSession() as session:
            tracks = list(YouTubeTranscriptApi(http_client=session).list(video_id))
            if not tracks:
                raise ExportError("This video has no available captions. Try another video.")
            track = min(tracks, key=lambda t: (
                0 if t.language_code == "en" else
                1 if t.language_code.lower().startswith("en-") else 2,
                t.is_generated,
            ))
            fetched = track.fetch()
            segments = tuple(
                Segment(" ".join(s.text.split()), s.start, s.duration)
                for s in fetched if s.text.strip()
            )
            if not segments:
                raise ExportError("YouTube returned empty captions for this video. Try again later.")
            return TranscriptResult(
                video_id, fetched.language, fetched.language_code,
                fetched.is_generated, segments,
            )
    except ExportError:
        raise
    except TranscriptsDisabled as error:
        raise ExportError("Captions are disabled or unavailable for this video. Try another video.") from error
    except AgeRestricted as error:
        raise ExportError("This video requires age verification. Its transcript can't be fetched by this app.") from error
    except (VideoUnavailable, VideoUnplayable) as error:
        raise ExportError("This video is unavailable, private, or restricted. Try another public video.") from error
    except RequestBlocked as error:
        raise ExportError("YouTube is blocking transcript requests on this connection. Wait a while and retry, or use another network.") from error
    except PoTokenRequired as error:
        raise ExportError("YouTube requires extra verification for this video's captions. Try another video.") from error
    except requests.Timeout as error:
        raise ExportError("YouTube took too long to respond. Check your connection and try again.") from error
    except requests.RequestException as error:
        raise ExportError("Couldn't connect to YouTube. Check your internet connection and try again.") from error
    except (YouTubeDataUnparsable, CouldNotRetrieveTranscript) as error:
        raise ExportError("YouTube couldn't provide this transcript. Retry later; the transcript library may need an update.") from error
