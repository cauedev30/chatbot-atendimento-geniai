import json
import traceback
from datetime import UTC, datetime


def _field(value: object) -> object:
    if isinstance(value, BaseException):
        return {"message": str(value), "stack": "".join(traceback.format_exception(value))}
    return value


class ConsoleLogger:
    """One JSON line per event on stdout; errors keep message and stack."""

    def _write(self, level: str, obj: dict[str, object], msg: str | None) -> None:
        line = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": level,
            "msg": msg,
            **{key: _field(value) for key, value in obj.items()},
        }
        print(json.dumps(line, ensure_ascii=False, default=str), flush=True)

    def info(self, obj: dict[str, object], msg: str | None = None) -> None:
        self._write("info", obj, msg)

    def warn(self, obj: dict[str, object], msg: str | None = None) -> None:
        self._write("warn", obj, msg)

    def error(self, obj: dict[str, object], msg: str | None = None) -> None:
        self._write("error", obj, msg)
