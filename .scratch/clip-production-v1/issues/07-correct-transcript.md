# 07: 文字起こしと不明区間を手修正する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/7

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が発言と話者判定を全体にわたり修正し、その結果を失わず再表示できる。

**Blocked by:** 06: 対象話者の発言を文字起こしする

**Status:** ready-for-agent

## 完了条件

+- [ ] 不明区間を試聴して発話・非発話に指定できる。
- [ ] 本文・時刻の修正、時刻付き発言の追加、他者発言の除外ができる。
- [ ] 修正は自動保存し、失敗時は入力を保持して手動再試行できる。
- [ ] 既存の区間一覧・字幕・クリップを自動変更しない。
