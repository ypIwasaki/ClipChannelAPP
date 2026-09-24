# 17: 別編集を作って旧編集を保持する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/17

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が順番を変えた新しい編集を作り、旧編集も利用できる。

**Blocked by:** 10: 区間を選び、順番を決めて編集用動画を作る; 14: 編集を明示保存し、完成動画を書き出す

**Status:** ready-for-agent

## 完了条件

+- [ ] 新しい編集用動画と別のAviUtl2プロジェクトを作る。
- [ ] 旧動画・旧プロジェクト・編集済み字幕・補助素材配置を保持し、新編集へ自動移行しない。
- [ ] 利用者が旧プロジェクトをAviUtl2で直接選んで開ける。
