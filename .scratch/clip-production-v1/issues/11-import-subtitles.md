# 11: 編集可能な字幕をAviUtl2へ渡す

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/11

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が元の文字起こしに対応した字幕をAviUtl2で編集できる。

**Blocked by:** 07: 文字起こしと不明区間を手修正する; 10: 区間を選び、順番を決めて編集用動画を作る

**Status:** ready-for-agent

## 完了条件

+- [ ] 最終クリップ範囲と重なる対象発言だけを結合後の時間軸へ写し、表示時刻を範囲内に収める。
- [ ] 字幕を焼き込まず編集可能なオブジェクトとして生成し、本文・件数・時刻・配置を確認する。
- [ ] 字幕の編集は元の文字起こしへ反映せず、再取込みは別字幕として追加する。
