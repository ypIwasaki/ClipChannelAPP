# 08: 頻出語から該当発言を確認する

**GitHub Issue:** https://github.com/ypIwasaki/ClipChannelAPP/issues/8

**参照元:** `docs/implements/spec-for-issues.md`（統合仕様書）

**What to build:** 利用者が頻出語から対象発言と元動画の位置を調べられる。

**Blocked by:** 07: 文字起こしと不明区間を手修正する

**Status:** ready-for-agent

## 完了条件

+- [ ] 名詞・固有名詞を初期対象とし、動詞・形容詞を追加選択できる。活用形をまとめ、意味推測による別表記・同義語の統合はしない。
- [ ] 登録語・除外語と長い語優先の規則を適用し、出現回数と該当発言件数を区別する。
- [ ] 同じ発言を重複表示せず、選択した発言の時刻から動画を確認できる。
- [ ] 再集計はCSVの別版として保存し、旧結果を保持する。
