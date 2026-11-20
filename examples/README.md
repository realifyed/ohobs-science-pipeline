# Core smoke fixture

`core-smoke-fixture.zip` contains synthetic calibration frames, one light,
truth files and the generator manifest. It is included in the source tree so
Core can be exercised in an isolated installation. Its FITS markers and checksums
are verified by `scripts/smoke_core.py`.

Regenerate the dataset with `osp-sim generate --profile standard --seed 1234
--height 32 --width 40 --lights 1 --masters 5 --output NEW_DIRECTORY`.
Archive the contents at the ZIP root. Keep it in a dedicated test workspace.
