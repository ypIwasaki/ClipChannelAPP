# 07: 文字起こしと不明区間を手修正する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/7

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が発言と話者判定を全体にわたり修正し、その結果を失わず再表示できる。

**Blocked by:** 06: 対象話者の発言を文字起こしする

**Status:** ready-for-agent

## 完了条件

- [x] 不明区間を試聴して発話・非発話に指定できる。
- [x] 本文・時刻の修正、時刻付き発言の追加、他者発言の除外ができる。
- [x] 修正は自動保存し、失敗時は入力を保持して手動再試行できる。
- [x] 既存の区間一覧・字幕・クリップを自動変更しない。

## Comments

2026-09-24: 既存の試聴・判定・発言編集に、各確定操作後のCSV別版自動保存を接続した。保存失敗時は画面上の編集結果を残し、再試行ボタンから同じ内容を保存できる。文字起こしCSVだけを更新し、区間一覧・字幕・クリップは変更しない。`python3 -m unittest discover -s tests -q` で22件成功。実画面のクリック操作は未確認。
