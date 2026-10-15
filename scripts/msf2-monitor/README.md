# Glamsterdam msf 2 overnight collector

Run `monitor.py` from the dedicated `qu0b/msf-2-overnight-20261013` worktree. It samples client APIs and private profiling metadata through the existing SSH aliases, and queries metrics and logs through the authenticated Panda CLI. All Ethereum requests are reads. No client or validator deployment is changed.

The checked-in user systemd units are installed in `~/.config/systemd/user/` on the monitoring workstation. `loginctl show-user ubuntu -p Linger` confirmed `Linger=yes`. The timer runs each minute through October 14, 2026, 08:00 UTC, then allows five minutes for final log ingestion. A successful final publication marks the state complete and disables the timer. Failed publication remains retryable.

State and deduplication live in `~/.local/share/msf2-monitor-20261013/`, mode restricted by the service umask. Evidence and the current findings are in [the overnight notes](../../md/msf-2-overnight-2026-10-13/README.md). The dedicated branch receives hourly commits and a final commit; the monitor never updates master or stages unrelated paths. Failed collections and publications appear in the summary and service journal.

```sh
systemctl --user status msf2-overnight-20261013.timer
journalctl --user -u msf2-overnight-20261013.service --since today
python3 -m unittest discover -s scripts/msf2-monitor -v
```

Use `systemctl --user disable --now msf2-overnight-20261013.timer` to prevent subsequent ticks; stopping an in-progress service is a separate action. This collector does not send alerts or file upstream issues. A workstation outage can interrupt capture. Existing Besu host timers continue storing private JFR checkpoints independently.

Published evidence excludes Docker environment variables, validator files, heap dumps and raw JFR events. Log excerpts pass credential redaction before save and publication. HPROF and JFR files remain private on their original hosts; their directory names, sizes and GC text can be shared. Raw log counts overlap between ingestion windows and must not be summed as event totals.
