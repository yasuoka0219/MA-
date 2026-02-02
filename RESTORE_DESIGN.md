# デザインを元に戻す方法

デザインの変更が気に入らない場合、以下の手順で元のデザインに戻すことができます。

## 方法1: バックアップファイルから復元

```bash
cp src/ma_tool/templates/ui_base.html.backup src/ma_tool/templates/ui_base.html
```

## 方法2: Gitで元に戻す

変更をコミットしていない場合:

```bash
git checkout src/ma_tool/templates/ui_base.html
```

変更をコミットしている場合:

```bash
git log --oneline src/ma_tool/templates/ui_base.html
# 変更前のコミットハッシュを確認

git checkout <コミットハッシュ> -- src/ma_tool/templates/ui_base.html
```

## 変更内容

以下の改善を行いました:

1. **サイドバー**: グラデーション背景、アクティブ状態の視覚的改善
2. **カード**: より柔らかい影、ホバーエフェクト
3. **ボタン**: グラデーション、アニメーション
4. **テーブル**: ホバーエフェクトの改善
5. **フォーム**: より洗練されたスタイル
6. **全体的**: より洗練されたカラースキームとアニメーション

## バックアップファイル

- `src/ma_tool/templates/ui_base.html.backup` - 変更前の状態
