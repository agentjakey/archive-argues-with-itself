# Site Worker

Static assets only. Do not deploy this folder by hand: `scripts/v2/build_release.py publish`
gates a release, copies it into `./release`, uploads it as a new version and deploys it.
`scripts/v2/build_release.py rollback` moves the deployment back. See docs/v2/HOSTING.md.
