# Changelog

Use this file only when you explicitly ask to update the changelog. Each new entry should include the date, time, and a 1-3 sentence summary of the changes that were made.

## 2026-08-16 3:31 PM America/Toronto

Fixed Toxic Spikes attribution in the additional statistics parser so Pokemon that set Toxic Spikes are correctly credited with inflicting the resulting poison status on switch-in targets. The later poison chip from that status is now correctly counted as residual indirect damage for the Toxic Spikes setter, and a regression test was added to lock in the behavior.

## 2026-08-16 3:32 PM America/Toronto

Adjusted status tracking for Rest so self-inflicted sleep is ignored for both `status_inflicted` and `status_received` counters. Added a focused regression test using the Showdown `|-status|...|slp|[from] move: Rest` protocol shape to keep that behavior stable.
