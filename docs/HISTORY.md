# Development history

`main` keeps the existing two r70 repository commits and the r87 repair commits.
`port-history` preserves 427 original shared-project commits through
`d60069db416ca2d6e3e334cde1e6349304ed2784`. That branch includes historical
kernel port and device-tree work. It does not supply files to the r87 build.
Original authors, dates, commit IDs and parent relationships are unchanged.
All original commits are authored by peiyuesheng666 <1203133791@qq.com>.
New commits use the account's GitHub noreply email.

The r87 commits are organized now from surviving patches and source receipts.
Their dates describe this organization; they do not pretend to be the original
development or device-test dates. The current release tag selects the final r87 project.
Original upstream revisions remain pinned in `provenance/`.

The release also contains an offline backup:

```bash
git clone sheng-port-history.bundle sheng-port-history
```

Old r70 release assets and its release tag are retired after r87 verification;
the two historical r70 commits remain reachable from main.
