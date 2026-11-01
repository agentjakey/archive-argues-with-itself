"""The audit pipeline: judge items built from recorded answers, deterministic gates, a panel of
model judges from two families, escalation, calibration against people's labels, and budgeted,
resumable runs. Collection-agnostic: every module takes a collection config
(config/collections/*.toml) and none names a collection. File formats: docs/formats/."""
