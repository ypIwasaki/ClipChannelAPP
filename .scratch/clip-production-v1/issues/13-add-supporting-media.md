# 13: 補助素材を追加して配置する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/13

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が画像・BGM・効果音を編集に加えて確認できる。

**Blocked by:** 10: 区間を選び、順番を決めて編集用動画を作る; 12: アプリからAviUtl2の画面と字幕を編集する

**Status:** ready-for-agent

## 完了条件

+- [ ] 外部の補助素材をデータ用フォルダへコピーし、元ファイルを変更しない。
- [ ] 配置を編集用動画に紐づけ、アプリから調整・プレビューできる。
- [ ] BGMは区間の継ぎ目を越えられ、追加時に長さを勝手に変えない。
