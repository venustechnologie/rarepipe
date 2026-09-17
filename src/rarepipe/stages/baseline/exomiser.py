"""Locating and running Exomiser. No network; the solver is invoked as a child process
that inherits whatever sandbox the stage runs under.
"""

from __future__ import annotations

import os
import re
import resource
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from rarepipe.resources.lock import sha256_file

JAR_GLOB = "exomiser-cli-*.jar"
OOM_PATTERNS = ("OutOfMemoryError", "Java heap space", "GC overhead limit exceeded")
REJECTION_PATTERNS = (
    "Unable to parse", "not a recognised", "Unsupported", "Could not read", "IllegalArgumentException",
    "genomeAssembly", "Unrecognised contig", "unknown contig",
)


@dataclass
class Installation:
    home: Path
    jar: Path
    version: str
    jar_sha256: str
    java: Path
    java_version: str
    data_dir: Path | None = None
    hg38_version: str | None = None
    phenotype_version: str | None = None


def find_java() -> tuple[Path, str] | None:
    candidates = [Path(p) for p in (os.environ.get("RAREPIPE_JAVA"), shutil.which("java")) if p]
    candidates += [Path("/opt/homebrew/opt/openjdk@21/bin/java"), Path("/usr/local/opt/openjdk@21/bin/java")]
    for java in candidates:
        if not java.is_file():
            continue
        try:
            out = subprocess.run([str(java), "-version"], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        text = (out.stderr or "") + (out.stdout or "")
        m = re.search(r'version "?(\d+)', text)
        if m and int(m.group(1)) >= 21:
            return java, text.splitlines()[0].strip() if text.strip() else "unknown"
    return None


def find_data_versions(data_dir: Path) -> tuple[str | None, str | None]:
    """Data directory holds <version>_hg38/ and <version>_phenotype/ folders."""
    hg38 = sorted(p.name.split("_")[0] for p in data_dir.glob("*_hg38") if p.is_dir())
    pheno = sorted(p.name.split("_")[0] for p in data_dir.glob("*_phenotype") if p.is_dir())
    return (hg38[-1] if hg38 else None), (pheno[-1] if pheno else None)


def locate(home: Path, data_dir: Path | None) -> Installation | None:
    jars = sorted(home.glob(JAR_GLOB))
    java = find_java()
    if not jars or java is None:
        return None
    jar = jars[-1]
    version = re.sub(r"^exomiser-cli-|\.jar$", "", jar.name)
    data = data_dir or (home / "data")
    hg38, pheno = find_data_versions(data) if data.is_dir() else (None, None)
    return Installation(home=home, jar=jar, version=version, jar_sha256=sha256_file(jar), java=java[0], java_version=java[1],
                        data_dir=data if data.is_dir() else None, hg38_version=hg38, phenotype_version=pheno)


@dataclass
class RunOutcome:
    exit_code: int
    wall_clock_seconds: float
    peak_rss_bytes: int
    log_path: Path
    out_of_memory: bool
    rejected_input: bool
    timed_out: bool
    tail: str


def run_job(install: Installation, job_file: Path, properties: Path, log_path: Path, *, max_heap: str = "7g",
            timeout_seconds: int = 6 * 3600) -> RunOutcome:
    cmd = [str(install.java), f"-Xmx{max_heap}", "-jar", str(install.jar), "analyse", "--analysis", str(job_file),
           f"--spring.config.location={properties}"]
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    t0 = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8") as log:
        log.write("# command: " + " ".join(cmd) + "\n")
        log.flush()
        try:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=install.home, timeout=timeout_seconds)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
    elapsed = time.monotonic() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # macOS reports ru_maxrss in bytes, Linux in kilobytes
    peak = max(after, before)
    peak_bytes = peak if peak > 1 << 32 else peak * 1024
    text = log_path.read_text(errors="replace")
    tail = "\n".join(text.splitlines()[-40:])
    return RunOutcome(exit_code=code, wall_clock_seconds=round(elapsed, 2), peak_rss_bytes=peak_bytes, log_path=log_path,
                      out_of_memory=any(p in text for p in OOM_PATTERNS),
                      rejected_input=code != 0 and any(p in text for p in REJECTION_PATTERNS), timed_out=timed_out, tail=tail)


VARIANT_COUNT_RE = re.compile(r"(?:Loaded|Processed|Analysing)\s+([\d,]+)\s+variant", re.I)


def variants_seen(log_text: str) -> int | None:
    counts = [int(m.group(1).replace(",", "")) for m in VARIANT_COUNT_RE.finditer(log_text)]
    return max(counts) if counts else None
