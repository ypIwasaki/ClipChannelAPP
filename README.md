# ClipChannelAPP

アーカイブ動画の取得、対象話者の文字起こし、切り出し、編集、管理を一つのアプリから扱うプロジェクトです。

現在は機能を段階的に実装中です。保存済みデータの閲覧、ローカル動画登録、認証不要URLの取得を扱う簡易画面があります。

```sh
python -m pip install -r requirements.txt
python -m clipchannel.app
```

動画取得とMP4変換には、別途 `ffmpeg` を実行パス上に用意してください。取得した元ファイルは `media/downloaded/` に保持し、登録したMP4は `media/originals/` に置きます。音声のみの結果は `media/audio/` に保存します。

- [別PCでの作業再開](docs/development-handoff.md)：読む順序、現在地、Git外のデータと実行環境
- [初版の編集受渡し方針](docs/implements/editor-handoff-scope.md)：動画一本化、字幕、保存・出力の簡易判定
- [初版範囲の縮小](docs/implements/initial-scope-pruning.md)：認証・特殊入力・配布対応の見送り
- [最新の話者・ASR検証](docs/implements/multi-speaker-validation.md)：指定動画の照合と10分の文字起こし
- [仕様再検討の状況](docs/implements/spec-review-status.md) / [合意履歴](docs/implements/spec-review.md)
- [原仕様（保持した草案）](docs/implements/spec.md) / [用語集](CONTEXT.md) / [設計判断](docs/adr/)

作業規則は [AGENTS.md](AGENTS.md) を参照してください。スキルは `.agents/skills/`、導入元の記録は `skills-lock.json` にあります。
