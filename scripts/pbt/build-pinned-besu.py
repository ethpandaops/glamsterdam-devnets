#!/usr/bin/env python3
"""Build the operator-pinned Besu and stateless library on Besu-2.

Checkouts must already exist at the exact commits. Uses an isolated Maven cache;
does not start an execution client or publish an image.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/data/pbt-1/migration-builds')
STATUS = ROOT / 'besu-build-status.json'
PINS = {
    'besu': '39377a2659f63c3bb230a5f57b4ef6846348f876',
    'besu-stateless': '62b752345cce00d9119f37c37d56eb9566269578',
}


def status(phase, **values):
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps({'phase': phase, 'time': time.time(),
                                     'commits': PINS, **values}, indent=2) + '\n')
    temporary.replace(STATUS)


def main():
    assert not STATUS.exists(), 'Inspect previous build before retrying'
    for name, sha in PINS.items():
        actual = subprocess.check_output(
            ['git', '-C', str(ROOT / name), 'rev-parse', 'HEAD'], text=True).strip()
        assert actual == sha
    status('pulling_toolchain')
    with (ROOT / 'besu-build.log').open('w') as log:
        subprocess.run(['docker', 'pull', 'eclipse-temurin:25-jdk'],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        toolchain = subprocess.check_output(
            ['docker', 'image', 'inspect', 'eclipse-temurin:25-jdk',
             '--format', '{{index .RepoDigests 0}}'], text=True).strip()
        assert '@sha256:' in toolchain
        commands = [
            ('library_tests_and_publish', 'besu-stateless',
             ['test', 'publishToMavenLocal']),
            ('besu_distribution', 'besu', ['installDist', '-x', 'test']),
        ]
        for phase, directory, tasks in commands:
            status(phase, toolchain=toolchain)
            subprocess.run([
                'docker', 'run', '--rm', '--name=pbt-1-besu-pinned-build',
                '--cpus=8', '--memory=16g', '--memory-swap=16g',
                '--volume', str(ROOT) + ':/work',
                '--workdir', '/work/' + directory,
                '--env', 'GRADLE_USER_HOME=/work/gradle-cache',
                toolchain, './gradlew', '--no-daemon', '--console=plain',
                '--max-workers=4', '-Dmaven.repo.local=/work/m2',
                '-Dorg.gradle.jvmargs=-Xmx8g', *tasks,
            ], check=True, stdout=log, stderr=subprocess.STDOUT)
        jars = list((ROOT / 'besu/build/install/besu/lib').glob('*stateless*.jar'))
        assert len(jars) == 1, f'Expected one resolved stateless JAR, got {jars}'
        digest = hashlib.sha256(jars[0].read_bytes()).hexdigest()
        published = list((ROOT / 'm2/org/hyperledger/besu').rglob('*.jar'))
        assert any(hashlib.sha256(p.read_bytes()).hexdigest() == digest
                   for p in published), 'Besu did not resolve the locally built stateless JAR'
        status('distribution_built', toolchain=toolchain,
               stateless_jar=str(jars[0]), stateless_jar_sha256=digest,
               library_tests_passed=True, migration_qualified=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        status('failed', error=str(exc))
        raise
