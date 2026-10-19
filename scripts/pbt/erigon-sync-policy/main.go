// Configure bounded, shared MDBX autosync thresholds on an already-open
// SAFE_NOSYNC preparation database. No keys or execution data are written.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"github.com/erigontech/mdbx-go/mdbx"
	"os"
	"path/filepath"
	"time"
)

type Report struct {
	Time              int64   `json:"time"`
	MDBXVersion       string  `json:"mdbx_version"`
	Flags             uint    `json:"flags"`
	PeriodSeconds     float64 `json:"period_seconds"`
	ThresholdBytes    uint    `json:"threshold_bytes"`
	InitialSyncForced bool    `json:"initial_sync_forced"`
}

// Live MDBX writer locks must not be shared across PID namespaces. Check the
// namespace and exact open database inode before opening any MDBX handle.
func verifyOwner(path string, ownerPID int) error {
	if ownerPID <= 0 {
		return fmt.Errorf("explicit live --owner-pid required")
	}
	owner := filepath.Join("/proc", fmt.Sprint(ownerPID))
	selfNS, err := os.Readlink("/proc/self/ns/pid")
	if err != nil {
		return err
	}
	ownerNS, err := os.Readlink(filepath.Join(owner, "ns/pid"))
	if err != nil || selfNS != ownerNS {
		return fmt.Errorf("owner must be alive in the helper's PID namespace")
	}
	db, err := os.Stat(filepath.Join(path, "mdbx.dat"))
	if err != nil {
		return err
	}
	fds, err := os.ReadDir(filepath.Join(owner, "fd"))
	if err != nil {
		return err
	}
	for _, fd := range fds {
		info, err := os.Stat(filepath.Join(owner, "fd", fd.Name()))
		if err == nil && os.SameFile(db, info) {
			return nil
		}
	}
	return fmt.Errorf("owner does not have the exact database inode open")
}

func configure(path string, period time.Duration, threshold uint) (r Report, err error) {
	if period <= 0 || period > 10*time.Second || threshold == 0 || threshold > 256*1024*1024 {
		return r, fmt.Errorf("policy exceeds bounded preparation limits")
	}
	info, err := os.Stat(filepath.Join(path, "mdbx.dat"))
	if err != nil || !info.Mode().IsRegular() || info.Size() == 0 {
		return r, fmt.Errorf("existing mdbx.dat required")
	}
	env, err := mdbx.NewEnv("pbt-sync-policy")
	if err != nil {
		return r, err
	}
	defer func() {
		if e := env.Close(); err == nil {
			err = e
		}
	}()
	// ACCEDE adopts the mode of the live owner. The guard below refuses both
	// durable-mode databases and MDBX's corruption-prone UTTERLY_NOSYNC mode.
	if err = env.Open(path, mdbx.Accede, 0600); err != nil {
		return r, err
	}
	flags, err := env.Flags()
	if err != nil {
		return r, err
	}
	// MDBX normalizes SAFE_NOSYNC to include NOMETASYNC internally. The
	// UTTERLY_NOSYNC extra bit must still be absent.
	if flags&mdbx.SafeNoSync == 0 || flags&mdbx.UtterlyNoSync == mdbx.UtterlyNoSync {
		return r, fmt.Errorf("expected SAFE_NOSYNC without UTTERLY_NOSYNC, flags=%x", flags)
	}
	if err = env.Sync(true, false); err != nil {
		return r, err
	}
	if err = env.SetSyncPeriod(period); err != nil {
		return r, err
	}
	if err = env.SetSyncBytes(threshold); err != nil {
		return r, err
	}
	actualPeriod, err := env.GetSyncPeriod()
	if err != nil {
		return r, err
	}
	actualBytes, err := env.GetSyncBytes()
	if err != nil {
		return r, err
	}
	// MDBX converts its fixed-point period through the platform monotonic
	// clock. Permit sub-100us rounding down, never a longer checkpoint period.
	if actualPeriod > period || period-actualPeriod > 100*time.Microsecond || actualBytes != threshold {
		return r, fmt.Errorf("threshold readback differs: period=%s bytes=%d, want %s %d", actualPeriod, actualBytes, period, threshold)
	}
	r = Report{Time: time.Now().Unix(), MDBXVersion: "mdbx-go v0.43.0", Flags: flags,
		PeriodSeconds: actualPeriod.Seconds(), ThresholdBytes: actualBytes, InitialSyncForced: true}
	return r, nil
}

func main() {
	db := flag.String("db", "", "existing live preparation chaindata")
	ownerPID := flag.Int("owner-pid", 0, "live database owner's PID in the same PID namespace")
	verifyOnly := flag.Bool("verify-owner-only", false, "verify namespace and open inode without opening MDBX")
	period := flag.Duration("period", 10*time.Second, "maximum time between sync checkpoints")
	threshold := flag.Uint("bytes", 256*1024*1024, "maximum unsynced bytes before checkpoint")
	flag.Parse()
	if err := verifyOwner(*db, *ownerPID); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if *verifyOnly {
		fmt.Println(`{"owner_verified":true,"database_opened":false}`)
		return
	}
	report, err := configure(*db, *period, *threshold)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err = json.NewEncoder(os.Stdout).Encode(report); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
