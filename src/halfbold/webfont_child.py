import resource
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


def limit_cpu_and_memory(cpu_seconds: int, memory_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except ValueError, OSError:
        return


def save_as_truetype(source: Path, target: Path) -> None:
    font = TTFont(source)
    font.flavor = None
    font.save(target)


def main(arguments: list[str]) -> int:
    source, target, cpu_seconds, memory_bytes = arguments
    limit_cpu_and_memory(int(cpu_seconds), int(memory_bytes))
    save_as_truetype(Path(source), Path(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
