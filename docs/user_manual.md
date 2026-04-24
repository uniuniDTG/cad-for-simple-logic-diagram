# Logic CAD ユーザーマニュアル（テンプレート DXF 含む）

論理回路図エディタは **ezdxf の Drawing を唯一のデータソース**とします。図面そのものは通常「アプリで新規作成 → 上書き保存」で得られる `.dxf` です。本書では、**ライブラリ用・図枠用のテンプレート DXF**を自分で用意する方法を中心に説明します。

---

## 1. 起動・基本操作

```text
python -m logic_cad.app.main
```

（推奨）仮想環境を有効化したうえで、プロジェクトルートから実行してください。

**デバッグ:** 標準出力に `[logic_cad:…]` ログを出すには **`--debug`** または環境変数 **`LOGIC_CAD_DEBUG=1`**。ルーティングの**大量ログ**はさらに **`LOGIC_CAD_DEBUG_ROUTING_VERBOSE=1`** が必要（デバッグ有効時のみ効く）。CLI 引数と各環境変数の一覧は **[開発者向け](developer.md)** を参照。

| 操作 | 内容 |
|------|------|
| パレットからドラッグ＆ドロップ | シンボル配置（ライブラリに登録された BLOCK 名） |
| シンボルドラッグ | 移動（離すと DXF の INSERT 座標が更新） |
| **ポート上をクリック** | 配線開始 → もう一方のポートで確定（Ctrl は不要） |
| **配線プレビュー中** | カーソル付近に長さ（mm）。手動配線はプレビュー上のマンハッタン累積、自動配線は始点ポートからマウスまでの直線距離 |
| **Ctrl + クリック（ページ跨ぎシンボルの本体・ポート以外）** | リンク先ページへ切替 |
| **Esc** | 配線の仮想線キャンセル、注釈（図形）の途中入力キャンセル |
| ホイール | カーソル位置を中心にズーム |
| 中ボタンドラッグ | パン |
| **Ctrl+Z / Ctrl+Y** | Undo / Redo |
| **Ctrl+C / Ctrl+V** | **シンボル**のコピー／貼り付け（複数選択可）。**両端が選択内にある配線**もまとめて複製。図枠・目次行などはコピー対象外。貼り付け位置の基準はキャンバス上の**直近のマウス位置**（無ければ表示領域の中心）。 |
| Delete | 選択の削除 |
| 左端「ページ」タブ・一覧 | ページ切替。各行は **`[レイアウト名] 説明`**（`page_desc` が空なら「（説明なし）」）。補足はツールチップ。右クリックで **ページ追加**（タブ名・改訂・説明）、**プロパティ**、**ページを複製…**（用紙内容・配線・注釈を別レイアウト名で複製。目次用レイアウト `0` / `0A` …は不可）、**ページを削除…**、**目次の再生成**。 |

**Edit**: **コピー**／**貼り付け**（上記シンボル＋内部配線）もここから実行できます。

**File**: New / Open / Save / Save As — いずれも DXF が対象です。**PDF にエクスポート…** は、先に **PDF 書き出し設定**（現状は「白黒で出力」の有無）を選び、続けて保存先を指定して全用紙を 1 つの PDF にまとめます（幾何はメモリ上の DXF を ezdxf の描画パイプラインで出力）。**ページ用のメニューはありません**（上記パネルから操作します）。

### 注釈（図形）ツール

左パネル（パレット上）の **直線 / 円 / テキスト** アイコンボタンは、**現在の用紙レイアウト**上にユーザー描画の `LINE`・`CIRCLE`・`TEXT` を追加します（レイヤ **`LD_ANNOTATION`**、`LD_APP` の種別は `USER_LINE` / `USER_CIRCLE` / `USER_TEXT`）。**自動配線・手動配線と同時には使えません**（一方をオンにすると他方はオフになります）。アクティブなツールは **水色の枠**で表示されます。

- **直線・円**: グリッドにスナップ。直線の 2 点目は **Shift** で水平／垂直（長い軸側）に拘束。新規は既定で実線（`CONTINUOUS`）。
- **テキスト**: クリックでダイアログから文字列入力し配置（位置はスナップなし）。新規の文字高さは既定 **4 mm**。
- **線種・文字・高さの変更**: オブジェクトをクリックして選択し、右側 **プロパティ** で編集して **適用**（直線・円は `CONTINUOUS` / `DASHED` / `CENTER`）。
- 選択して **Delete** で削除。描画・プロパティ変更は既存の **Undo** に含まれます。

### PDF と日本語表示（□ について）

- **PDF**: エクスポート時、システムに見つかる日本語対応フォントへフォールバックしてグリフを描画します。ポート用レイヤ（`LD_PORT` / `LD_PORT_…`）上の図形は PDF には含めません（編集用の接続点のため）。
- **BricsCAD など他 CAD で □ になる場合**: DXF の **テキストスタイル（STYLE）が参照しているフォント**に CJK グリフが無いことが多いです。PDF のフォールバックだけでは CAD 上の表示は変わりません。図枠テンプレートや CAD 側でスタイルのフォントを日本語対応の TrueType に合わせてください。

---

## 2. アプリが読み込む DXF の種類

```text
【いつもの作業ファイル】
  任意の名前の .dxf（Save で出力）

【起動時にマージするアセット（任意・推奨）】
  logic_cad/assets/symbol_library.dxf   … 固定シンボルの BLOCK 定義
  logic_cad/assets/frame_template.dxf      … 図枠テンプレ（任意・新規ページ時に `generate/` より先に検索）

【開発用サンプル（アセットは上書きしない）】
  generate/frame_template.py → generate/frame_template.dxf（A4 横。§4-3）

【存在しなければ】
  symbol_library.dxf が無い → NOT スタブと PAGE_TO / PAGE_FROM だけ自動生成
```

- **AND/OR** は `symbol_library` には含めません。アプリが入力数に応じて `AND_n` / `OR_n` ブロックを **動的生成**します。
- `symbol_library.dxf` に **NOT** が無くても、アプリ側でスタブ NOT を補うため、最低限の動作には足ります。本番ではライブラリに正式な NOT を入れるとよいです。
- dxfファイルはAutoCADおよび高互換CAD(例:BricsCAD)での編集を想定しています。互換が低いCADの場合、XDATAなどのメタデータ破損のリスクがあります。
---

## 3. `symbol_library.dxf` の作り方（テンプレート）

### 3-1. 置き場所

```text
logic_cad/assets/symbol_library.dxf
```

このパスにファイルを置くと、**新規ドキュメント作成時**（`LogicDiagram.new()`）に **BLOCK 定義がマージ**されます。

**再読み込み:** メニュー **テンプレート** → **シンボルライブラリを再読み込み** で、上記パスのファイルを**現在開いている図面**へ取り込み直せます（図枠の `frame_template.dxf` は対象外）。既存と**同名のブロック**は、ブロック定義の**中身が置き換わり**、配置済みのシンボルも新しい形状で表示されます。ライブラリ側を編集する際は、**寸法・ポート位置・ブロック原点（BASE）**は極力変えないことを推奨します（大きく変えると配置や配線の見かけがずれやすくなります）。取り込み後に**保存**すると、作業用 DXF にブロック定義が書き込まれます。

### 3-2. CAD（BricsCAD / AutoCAD 等）で作る手順の概要

1. **新規図面**を作成し、保存先を上記パスにする（または後でコピー）。
2. **レイヤ**を用意する（下表）。色・線種は環境に合わせて構いませんが、**レイヤ名**はアプリ仕様と一致させてください。
3. **BLOCK 定義**を作成（名前は英数字・`_` など。`*` で始まる名前はアプリがインポートしません）。
4. ブロック編集画面で次を配置する。
   - **形状**: `LINE` / `ARC` など → レイヤ **`LD_SYMBOL`**（推奨）
   - **ポート**: `POINT` だけを置き、その **レイヤ名**でポート種別を表す（次項）
   - **表示テキスト**: `ATTDEF`、タグ **`SYM`**、レイヤ **`LD_TEXT`**（配置後アプリが値を書き込みます）
5. ブロック原点（BASE）を、配置しやすい位置に設定。
6. `symbol_library.dxf` を保存。

### 3-3. ポート用レイヤ名（必須パターン）

POINT を**接続端子**として使います。レイヤ名は次の形式です。

```text
LD_PORT_IN{番号}_{LOGIC|VALUE|MULTI}
LD_PORT_OUT{番号}_{LOGIC|VALUE|MULTI}
```

例:

- 入力 0（論理）: `LD_PORT_IN0_LOGIC`
- 出力 0（論理）: `LD_PORT_OUT0_LOGIC`

番号は 0 始まりで連番にしてください（アプリのポートキーと一致させるため）。

### 3-4. 配置できるテキスト（レイヤ × 属性タグ）

シンボルブロック内の**文字**は、基本は **DXF の `ATTDEF`（属性定義）** で置きます。  
**レイヤ名で「ラベル種別」を分けない**運用です。`LD_LABEL0` のようなレイヤ名は**仕様にありません**。  
「どのラベルか」は **ATTDEF のタグ名**（例: `SYM`, `LABEL0`）で区別します。

#### 表 1 — テキストを置くレイヤ（ブロック定義内）

| レイヤ | 置くもの | アプリの扱い |
|--------|----------|--------------|
| **`LD_TEXT`** | **`ATTDEF`**（推奨） | エディタで表示。位置・高さ・回転・幅・揃えは DXF の ATTDEF に従う |
| **`LD_SYMBOL`** | **`ATTDEF`**（可） | 図形と同じレイヤに文字を置く場合。`LD_TEXT` と同じく表示対象 |
| **`LD_ANNOTATION`** | `TEXT` / `ATTDEF` など | 注釈用レイヤ（ライブラリでは通常不要） |

※ `LD_SYM` は**存在しません**。形状は **`LD_SYMBOL`**、属性テキストは **`LD_TEXT` + ATTDEF** が推奨です。

#### 表 2 — ATTDEF のタグ名（属性名）と意味

| タグ名 | 意味（何の文字か） | プロパティ連動 |
|--------|-------------------|----------------|
| **`SYM`** | 素子の**表示名・参照**（回路名・部品名） | **あり**。プロパティの「SYM」で編集。DXF の**非表示**も反映 |
| **`STATIC_LABEL0`** | **ゲート左上**の固定ラベル（例: `A` / `OR`） | **動的 AND/OR のみ** UI が特別扱い。ライブラリの一般シンボルでは「描画のみ」 |
| **`STATIC_LABEL1`** など | 追加の固定ラベル（例: R/S など） | 描画のみ（タグ名は自由に増やせる） |
| **`LABEL0`** / **`LABEL1`** … | **ユーザー任意**のラベル | 描画のみ。タグ名は自由 |

**補足:** エディタのプレビューは **`SYM`・`STATIC_LABEL{n}`・`LABEL{n}`** の ATTDEF のみ描画します。それ以外のタグ（例: 外部 CAD の独自属性）は DXF 上はそのままですが**描画しません**。`SYM` だけプロパティの表示／非表示と連動します。

### 3-5. 参照しやすい最小例（概念）

ブロック名 `DEMO_RELAY`:

- `LD_SYMBOL` に矩形の `LINE`
- 左に `POINT`（レイヤ `LD_PORT_IN0_LOGIC`）、右に `POINT`（レイヤ `LD_PORT_OUT0_LOGIC`）
- `ATTDEF` / `SYM` を `LD_TEXT` に配置

寸法は **図面単位＝mm 想定**で、座標が大きすぎるとキャンバス上で扱いにくくなります。

### 3-6. Python（ezdxf）で空ファイルから足す例

既存 CAD が無い場合のスケルトン例です（座標は任意）。

```python
import ezdxf
from pathlib import Path

doc = ezdxf.new("R2010", setup=True)
for name in ("LD_SYMBOL", "LD_TEXT", "LD_PORT_IN0_LOGIC", "LD_PORT_OUT0_LOGIC"):
    if name not in doc.layers:
        doc.layers.add(name)

blk = doc.blocks.new("MY_BLOCK")
blk.add_line((0, 0), (4, 0), dxfattribs={"layer": "LD_SYMBOL"})
blk.add_line((4, 0), (4, 3), dxfattribs={"layer": "LD_SYMBOL"})
blk.add_line((4, 3), (0, 3), dxfattribs={"layer": "LD_SYMBOL"})
blk.add_line((0, 3), (0, 0), dxfattribs={"layer": "LD_SYMBOL"})
blk.add_point((0, 1.5), dxfattribs={"layer": "LD_PORT_IN0_LOGIC"})
blk.add_point((4, 1.5), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})
blk.add_attdef("SYM", "MY_BLOCK", (0.5, -0.5), dxfattribs={"layer": "LD_TEXT", "height": 0.35})

Path("logic_cad/assets/symbol_library.dxf").parent.mkdir(parents=True, exist_ok=True)
doc.saveas("logic_cad/assets/symbol_library.dxf")
```

---

## 4. `frame_template.dxf`（図枠テンプレ）

**設計意図:** 図枠は **あえて DXF（テンプレ）に置き**、BricsCAD 等で **自由に編集**できるようにしている。アプリは主に **フィールド本文の更新**などに留め、ユーザーのレイアウト・向き・書式を勝手に上書きしない方針とする（実装もその前提で変えないこと）。

### 4-1. 現状のコードとの関係

`ensure_minimal_page` は、レイアウトに **VPORT（XDATA `type=VPORT`）がまだ無い** とき、次の順でテンプレを探して **用紙レイアウト用ブロックへコピー**します（幾何ビューにそのまま表示されます）。

1. `logic_cad/assets/frame_template.dxf`
2. リポジトリ直下 `generate/frame_template.dxf`

いずれも無い、またはコピー後も **`LD_VPORT` 上の VPORT 矩形が無い**場合でも、アプリは **図枠・VPORT を自動では追加しません**（テンプレまたは CAD で用意してください）。

`import_frame_template(doc, layout_name, path=None)` を直接呼ぶこともでき、戻り値はコピーしたエンティティ数です。ログ: `LOGIC_CAD_DEBUG_SYMLIB=1` で `[symlib] frame_template: ...`、`LOGIC_CAD_DEBUG=1` で `[logic_cad:frame] ...`。

テンプレの作り方は次のとおりです。

### 4-2. テンプレに含めるとよいもの

- 図枠・区画の `LINE` / `LWPOLYLINE` → レイヤ **`LD_FRAME`**
- 将来アプリが解釈する **仮想ビューポット**用の閉じた矩形 → **`LD_VPORT`**（1 レイアウト 1 つが仕様上の目安）
- **タイトル帯（任意）**: ブロック **`LD_PAPER_FRAME`**（外枠は **`LD_FRAME`**、表題用 **`ATTDEF` は `LD_FRAME_TEXT`**）を定義し、用紙ブロック内に **`INSERT`** を 1 つ置きます。INSERT の XDATA `LD_APP` で **`type:PAPER_FRAME`** を付けます。**リフレッシュ**は **`DWG_NO` / `PAGE_NAME` / `PAGE_DESC` / `PAGE_REV` の ATTRIB だけ**更新します（ATTDEF の既定文字列に `{{…}}` があればプレースホルダ展開）。**それ以外の TAG の ATTRIB** は触りません。**図枠 INSERT が無いレイアウトではリフレッシュは何もしません**（旧 `FRAME_TEXT` `MTEXT` は解釈しません）。
- **目次表（推奨）**: ブロック **`CONTENTS_HEADER`** / **`CONTENTS_ROW`**（セル枠は **`LD_CONTENTS_FRAME`**、セル内 **`ATTDEF` は `LD_CONTENTS_TEXT`**）。タグは **`PAGE_NAME`**（一覧のレイアウト名列）、**`PAGE_DESC`**、**`PAGE_REV`**。テンプレの **modelspace** に閉じた **`LWPOLYLINE`** を **`LD_CONTENTS_AREA`** に置くと、その矩形を **目次レイアウトだけ**にコピーし、**「目次を再生成」**でグリッドの **`INSERT`** を敷き詰めます。**ページとセルの対応は列優先（N 字）**です：各列を **上→下**に並べ、列が左から右へ進みます。グリッドのセル数に足りない分は **空行**でも **`CONTENTS_ROW` を配置**し、`PAGE_NAME` 等は空のまま **`LD_CONTENTS_FRAME` の枠だけ**残します（表の外形は常に一定）。**エディタ**では目次シート上の自動生成セル（`TOC_HEADER` / `TOC_ROW`）は **選択・移動・削除・回転**できません（図枠と同様）。**Ctrl+クリック**で行内の **`PAGE_NAME` が指す用紙**へ切り替えられます（`PAGE_REF` のページ跨ぎと同じ操作感）。**目次以外の用紙**では **`LD_CONTENTS_AREA` 上の図形は取り込み直後に削除**されるため、他 CAD で印刷してもガイド矩形は出ません。**エディタ**では目次シート上の **`LD_CONTENTS_AREA`** も描画しません（DXF には残します）。**保存**時、目次シートが 1 枚でもあれば **`LD_CONTENTS_AREA` 画層をオフ**にして、外部 CAD で開いたときのガイドも抑止します。入力行が足りない場合は、目次用のレイアウト名スロット **`0`**・**`0A`**・**`0B`** … のうち、まだ無い名前の **用紙レイアウト**を自動追加します。セルに収まらない場合は従来どおり **`LD_TOC` 上の `MTEXT`** にフォールバックします。

| `TAG`（更新対象） | 値の出所 | ATTDEF 既定文字列の例 |
|-------------------|----------|------------------------|
| `DWG_NO` | **Project settings → Drawing properties…**（`$PROJECTNAME`） | `{{DWG_NO}}` |
| `PAGE_NAME` | レイアウト（タブ）名 | `{{PAGE_NAME}}` |
| `PAGE_DESC` | ページプロパティの説明 | `{{PAGE_DESC}}` |
| `PAGE_REV` | ページプロパティの改訂番号 | `Rev: {{PAGE_REV}}` など |

標準の `generate/frame_template.py` は **上記ブロック＋modelspace の INSERT 1 つ**を**例として**出力します（座標は CAD で自由に変更可）。**新規図面**の初回のみ `frame_template.dxf` を取り込みます。**保存済み DXF を Open** したときは、**ファイル内の枠をそのまま**使います（起動時の検索パスだけでは上書きしません）。

**図枠の差し替え（エディタ）:** メニュー **テンプレート** → **図枠テンプレートを適用…** で任意の `.dxf` を選ぶと、**全用紙ページ**について `LD_PAPER_FRAME` 等のブロック定義と、各ページにコピーされている図枠・目次ガイドを**置き換え**ます（`generate/frame_template.py` と**同系のブロック名・構造**を推奨）。**目次グリッド**は適用後に再生成されます。検証用に **`python generate/frame_template2.py`** で英語ラベル版の `generate/frame_template2.dxf` を出力できます（既定のテンプレ検索順には含めません。適用ダイアログでファイルを指定してください）。

**ページの一意な識別子は ezdxf の用紙レイアウト名（CAD のタブ名）だけ**です。名前は **ASCII の英数字とアンダースコア**（`^[A-Za-z0-9_]+$`）にしてください。

用紙レイアウトの **LAYOUT XDATA（`LD_APP` / type PAGE）**では、ユーザー向けの正規メタは **`page_desc`**（説明）と **`page_rev`**（改訂）です（`ver` / `uid` / `type` はシステム用）。**Save** 時、用紙レイアウトの **CAD タブ順（`taborder`）**は **目次レイアウトを先頭に**、そのほかは **レイアウト名の自然順**（連続する数字部分は数値として比較するので `2` → `10` → `11`）に揃えます。

**目次用紙のレイアウト名:** **`0`**（定数 `TOC_LAYOUT_NAME`）、続くシートは **`0A`**、**`0B`**、… とします（予約パターン `^0[A-Z]*$`）。通常の用紙名はこのパターンに当てないでください。ページリンク（PAGE_REF）のリンク先は XDATA キー **`target_layout`** に **対象レイアウト名**を格納します。

外部 CAD でだけ図面を作る場合は、**後からアプリで開いて検証**することを推奨します。

### 4-3. サンプル生成（`generate/`）

**生成スクリプト**は `logic_cad/assets` を触らず、リポジトリ直下の **`generate/`** に出力します（既存アセットの上書きを避けるため）。

```bash
python generate/frame_template.py
```

出力: `generate/frame_template.dxf`（A4 横 297×210 mm、**図枠は用紙左下 (0,0)〜右上**、`LD_PAPER_FRAME` ブロック＝`LD_FRAME` の外枠＋**`LD_FRAME_TEXT` の ATTDEF ×4**、**`CONTENTS_HEADER` / `CONTENTS_ROW`**、**`LD_CONTENTS_AREA`** の閉じた矩形、modelspace に **`type:PAPER_FRAME` の INSERT**）。サンプルには **`LD_VPORT` は含めません**。**挿入単位は mm**（`$INSUNITS` = 4）です。

開き直し・新規ページ時はレイアウトの **用紙サイズを A4 横に設定**し、余白を 0 にそろえ、**メイン用の用紙ビューポート（VIEWPORT 実体）を 1 本だけ残し**、画層 **`VIEWPORTS` に載せてその画層をオフ**にします（枠が見えないようにするため。CAD 互換のため実体は残します）。**ビューポート枠のプロット**もオフにします。あわせて、用紙空間に残りがちな **レイヤ `0` の 237.6×168 mm 前後の矩形**（A4 横の約 80%＝各辺 10% 相当の印刷域ガイド）を削除します。DXF 標準の **レイヤ `0` 自体は必須**ですが、新規図面は寸法矢印用の補助ブロックを増やさない設定にしています。

`assets` に置けば **検索順が先**になります。別パスだけ使う場合は `import_frame_template(..., path=Path(...))` で明示してください。

### 4-4. 多ページ確認用 DXF（`generate/many_pages_dxf.py`）

**目的:** 左端の **ページ一覧**、**タブ順**、**目次**、**図枠の `PAGE_DESC` / `PAGE_REV`** など、枚数が多いときの動作を手元で試すための DXF を、リポジトリルートからワンコマンドで作ります（本番図面ではなく検証専用）。

**実行例:**

```bash
python generate/many_pages_dxf.py
python generate/many_pages_dxf.py 120 -o C:/temp/many.dxf
```

- **既定:** 用紙レイアウト **100** 枚。1 枚目は **`Layout1`**、追加は **`P2`** … **`P100`**（枚数を変えれば最後の名前が変わります）。
- **出力既定:** `generate/many_pages_test.dxf`（`-o` / `--output` で変更可）。
- **説明・改訂:** 各用紙レイアウトの LAYOUT XDATA に、**`page_desc`**（例: 「確認用 P5：全100枚中5枚目。一覧・図枠・目次表示のテスト」）と **`page_rev`**（10 枚ごとに `"1"`, `"2"`, … と増えるサンプル）を自動で入れます。エディタのページ行の **説明**列や、§4-2 の図枠・目次プレースホルダと対応する表示の確認に使えます。

---

## 5. 作業用 DXF（ユーザーが編集する本番図面）

1. **File → New** で空に近い状態から開始（初回ページ・**標準レイヤ**・レイアウト XDATA・用紙設定は自動。**`LD_VPORT` 矩形はテンプレに含まれる場合のみ**取り込み）。新規・読み込みとも **図面の挿入単位は mm**（`$INSUNITS` = 4）に正規化されます（BricsCAD の単位表示が m にならないよう揃えています。座標値は変えません）。
2. **Project settings → Drawing properties…** で **図面番号**（`{{DWG_NO}}` / `$PROJECTNAME`）を設定できます。保存後、BricsCAD でも同じヘッダを参照できます。
3. **パレット**に表示されるのは、`symbol_library.dxf` から取り込んだ BLOCK 名などです（AND/OR は別途種別として配置）。
4. **Save / Save As** で `.dxf` を保存。
5. BricsCAD 等で同じファイルを開いて共同編集することも可能です（XDATA `LD_APP` と UUID を壊さないよう注意）。

---

## 6. DXF 設定仕様まとめ（レイヤ × エンティティ × ATTDEF）

アプリは **`logic_cad/core/model/constants.py`** の定数名と一致するレイヤを前提にします。CAD でテンプレートを作るときは **表の「レイヤ名」をそのまま**使うと安全です。

### 6-1. 標準レイヤ（定数対応）

| レイヤ名（定数） | 主なエンティティ | 役割 |
|------------------|------------------|------|
| **`LD_SYMBOL`**（`LAYER_SYMBOL`） | `LINE`, `LWPOLYLINE`, `ARC`, `CIRCLE`, `HATCH`, … | シンボル**外形**（ブロック内の描画線・塗り） |
| **`LD_TEXT`**（`LAYER_TEXT`） | `ATTDEF`（推奨） | **`SYM` 等**の属性定義 |
| **`LD_FRAME_TEXT`**（`LAYER_FRAME_TEXT`） | `ATTDEF`（`LD_PAPER_FRAME` 内） | **図枠タイトル帯**（`DWG_NO` 等） |
| **`LD_PORT`**（`LAYER_PORT`） | 互換・予備 | ポート判定には使わず、**実ポートは必ず後述の `LD_PORT_IN…` / `OUT…`** |
| **`LD_WIRE_LOGIC`**（`LAYER_WIRE_LOGIC`） | `LWPOLYLINE`（XDATA type=WIRE, unit=LOGIC） | **論理**配線 |
| **`LD_WIRE_VALUE`**（`LAYER_WIRE_VALUE`） | `LWPOLYLINE`（XDATA type=WIRE, unit=VALUE） | **値**配線 |
| **`LD_WIRE_BRIDGE`**（`LAYER_WIRE_BRIDGE`） | `ARC` | **交差部のブリッジ**（自動） |
| **`LD_ANNOTATION`**（`LAYER_ANNOTATION`） | `POINT`, `TEXT` 等 | 将来・拡張の注釈 |
| **`LD_FRAME`**（`LAYER_FRAME`） | `LWPOLYLINE`, `LINE` | **図枠** |
| **`LD_CONTENTS_AREA`**（`LAYER_CONTENTS_AREA`） | 閉じた `LWPOLYLINE` | **目次表の敷き詰め領域**（目次レイアウトのみ保持・非目次では削除） |
| **`LD_CONTENTS_FRAME`**（`LAYER_CONTENTS_FRAME`） | `LWPOLYLINE`（`CONTENTS_*` ブロック内） | **目次セル枠** |
| **`LD_CONTENTS_TEXT`**（`LAYER_CONTENTS_TEXT`） | `ATTDEF`（`CONTENTS_*` ブロック内） | **目次セル文字** |
| **`LD_VPORT`**（`LAYER_VPORT`） | 閉じた `LWPOLYLINE`（XDATA type=VPORT） | **編集キャンバス相当の矩形** |

### 6-2. ポート専用レイヤ（POINT のみ）

正規表現で解釈されます（`logic_cad.core.model.index_store` と同じ）:

```text
LD_PORT_(IN|OUT)(番号)_(LOGIC|VALUE|MULTI)
```

- 例: `LD_PORT_IN0_LOGIC`, `LD_PORT_OUT0_LOGIC`
- **番号は 0 始まり**。アプリ内部のポートキー（例: `IN0_LOGIC`）と対応。

### 6-3. テキスト（レイヤ × 属性）

**ブロック内のテキスト**の詳細は **§3-4（表 1・表 2）** にまとめています。ここでは要点だけ:

- **レイヤ:** 属性テキストは **`LD_TEXT` に ATTDEF** を置くのが基本（`LD_SYMBOL` 上の ATTDEF も可）。
- **タグ名:** **`SYM`**（表示名）、**`STATIC_LABEL0`**（ゲート用）、**`LABEL0` 等**（任意ラベル）。
- **レイヤ名 `LD_LABEL0` は使わない**（ラベル種別は **ATTDEF のタグ**で区別）。

**まとめ:** 形状は **`LD_SYMBOL`**、属性テキストは **`LD_TEXT` + ATTDEF タグ**、接続点は **`LD_PORT_IN…` / `OUT…`**。

---

## 7. トラブルシューティング

| 現象 | 確認すること |
|------|----------------|
| パレットにシンボルが出ない | `symbol_library.dxf` のパスと、BLOCK 名が `*` で始まっていないか |
| ポートに繋がらない | POINT のレイヤ名が `LD_PORT_IN*_LOGIC` 等の規則か |
| NOT が無いと言われる | ライブラリに `NOT` ブロックを追加するか、アプリのスタブに任せる |
| インポートエラー | DXF バージョン・破損、`Importer` の制約。別名でブロックを分割して再保存 |

---

## 8. 関連ファイル（開発者向け）

| パス | 役割 |
|------|------|
| `logic_cad/core/logic_diagram.py` | 編集 API のファサード（`LogicDiagram`） |
| `logic_cad/core/services/layout_service.py` | `import_symbol_library` / `reload_symbol_library` / `import_frame_template` / `apply_frame_template_from_path` / ページ初期化 |
| `logic_cad/core/model/constants.py` | レイヤ名・グリッド・ルーティング定数など |
| `logic_cad/core/model/index_store.py` | UID／ポート／ワイヤのインデックス、ポートレイヤ名の正規表現 |
| `logic_cad/core/model/xdata.py` | `LD_APP` / UUID |
| `logic_cad/core/pages/` | 用紙レイアウト名順・ページメタ・`PAGE_REF`・目次グリッド幾何 |
| `logic_cad/core/dxf/dxf_repository.py` | 新規／読込／保存・標準レイヤ |
| `logic_cad/core/undo/` | Undo／Redo 用のデルタとエンティティのシリアライズ |
| `logic_cad/tests/test_symbol_library_import.py` | ライブラリ取り込みの自動テスト |
| [`developer.md`](developer.md) | `--debug`・`LOGIC_CAD_*`・ルーティング試験用 env |

---

更新日: レイヤ／ATTDEF 仕様は `logic_cad/core/model/constants.py` と `logic_cad/core/model/index_store.py` のポート正規表現と併せて確認してください。
