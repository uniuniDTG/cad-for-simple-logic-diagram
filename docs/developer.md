# 開発者向け

デバッグログ、起動引数、環境変数の対応をまとめます。実装の入口は主に次のとおりです。

- 一般ログ: `logic_cad/core/debug/debug_log.py`（`logic_cad_log` / `logic_cad_log_separator`）
- シンボルライブラリ: `logic_cad/core/debug/debug_symlib.py`（`symlib_log`）；再読み込み API は `logic_cad/core/services/layout_service/` パッケージ（`reload_symbol_library` 等、`__init__.py` から従来どおり再エクスポート）
- 新規図面の先頭紙レイアウト名: `logic_cad/core/model/constants.py` の `FIRST_PAGE_NAME`（`LogicDiagram.new` が ezdxf 既定の1枚目をこの名前へリネーム。既存 DXF を開いたときはファイル内の名前のまま）
- 図枠テンプレートの明示パス適用・置き換え: `logic_cad/core/services/layout_service/layout_frame_template.py`（`apply_frame_template_from_path`；`layout_service` パッケージからも利用可）
- 目次（TOC）フォールバック: `logic_cad/core/services/toc_frame_service.py`（`--debug` か root logger が `INFO` 以下のとき）
- ステータスバー: キャンバス上のカーソル位置を DXF 図面座標 (mm) で表示。シーン座標は `dxf_from_scene_pos`（`logic_cad/ui/snap_utils.py`）で mm に変換
- **プロパティパネル**: `logic_cad/ui/panels/property_panel/`。**インポートパスは不変**（`from logic_cad.ui.panels.property_panel import PropertyPanel`）。`widget.py` が QWidget とスタック構成・共通ポート表示、`symbol_section.py` / `wire_section.py` / `block_edit_section.py` が機能別 mixin、`helpers.py` が QMessageBox 共通化と `port_sort_key`。
- **インアプリ・ブロック編集（BEDIT 風）**: 左タブ「ブロック」。左の一覧は `list_block_editor_block_names`（`logic_cad.core.services.layout_service`）。`PAGE_FROM` / `PAGE_TO` はブロック編集一覧に出す（クロスページ・リンク用定義の編集）。`INPAGE_FROM` / `INPAGE_TO` は一覧に出さない（インページ・リンクは専用 UI）。これらはいずれもパレット（`list_palette_block_names`）からは隠す。編集は **スクラッチ `Drawing`**（`BlockEditSession` / `logic_cad/core/services/block_edit_session.py`）上で行い、**本体へ適用**で `doc.blocks[name]` の中身を差し替え。**適用はメインの `HistoryService` に積まない**（スクラッチ側の Undo のみ）。新規/開く/閉じる/図枠・シンボルライブラリ操作は `BlockEditPanel.request_end_session_for_nav` で先にセッション終了。**同一 `LD_PORT_*` レイヤへの POINT 重複は禁止**（`block_edit_helpers.port_layer_is_taken`）。キャンバス実装: `logic_cad/ui/symbol_block_editor/`
- **INPAGE_REF（同一紙面上のリンク）**: LD_APP の `sym` + ATTRIB `SYM` が表示文字。自動採番は `inpage_link_name_auto` が省略/`"1"` のペアだけが ※1, ※2…（手動 `"0"` のペアは連番を消費しない）。プロパティから手動文字列を設定するとペア両端が同期され、`refresh_inpage_ref_syms_on_layout` が他の自動ペアの番号を詰め直す。実装: `logic_cad/core/pages/inpage_ref.py` / `SymbolService.set_inpage_ref_link_display`
- 起動引数: `logic_cad/app/main.py`
- ルーティングプロファイルの env 上書き: `logic_cad/core/routing/profile.py`（`apply_routing_env_overrides`）
- シンボル移動後の再配線の区間計測: `logic_cad/core/debug/routing_perf.py`（`LOGIC_CAD_PERF_ROUTING=1`）
- キャンバス上の QGraphicsItem の Z 順（ヒットテスト・重なり）: `logic_cad/ui/scene_item/z_order.py`（ルーティング一時オーバーレイの 10000 台は同ファイル docstring のとおり別帯）
- **ユーザースケッチツールバー**: `logic_cad/ui/main_window/tool_bridge.py` のスケッチ系 `QPushButton` は相互排他（`exclusive_tool_buttons`）。リリース前または大きめの UI リファクタ後は、各スケッチツールの ON/OFF・スケッチ ON 時のワイヤツール解除が意図どおりか実機で一度確認するとよい。
- OSNAP（限定実装）: `logic_cad/ui/scene_item/osnap.py`（`LD_PORT` のみ対象。配線モード（自動/手動）でポートスナップに利用、それ以外は `snap_to_grid`）
- ポートキー解析（IN/OUT/INOUT）: `logic_cad/core/model/port_key.py`（`startswith("IN")` のような曖昧判定を避ける）
- `WIRE_BRANCH` ポート仕様: `INOUT0_MULTI` 単一ポート（多接続可）。`scene.py` のクリック正規化、`port_src_dst_solver.py` の制約、`symbol_item.py` の丸色判定（3本以上で白）を合わせて更新する。
- ユーザー直線ツール: ツールバーの直線ボタンを右クリックすると、次に描く線の線種（CONTINUOUS / DASHED / CENTER）を選べる。状態は `DiagramScene` の `user_sketch_line_default_linetype` / `set_user_sketch_line_default_linetype`
- メインキャンバスの注釈テキスト配置・ブロック編集の `LD_TEXT` 配置: 共通ダイアログ `logic_cad/ui/dialogs/user_text_place_dialog.py` の `prompt_dxf_text_string_and_height`（文字列＋字高 mm）。メインの既定字高の初期値は `USER_TEXT_DEFAULT_HEIGHT_MM`
- 文字列の検索・置換: `logic_cad/core/services/text_find_replace.py`（`TextSearchHit` / `list_text_search_hits`、対象は `SYM` / `LABEL*` と `USER_TEXT` 等）。`logic_cad/ui/text_search_navigate.py`（`apply_text_search_hit`）。UI: `find_replace_dialog.py`、Ctrl+F で**非モーダル**検索（前検索 / 次検索 / キャンセル、F3 / Shift+F3、パネル非表示時もメインにフォーカスがあれば可）。**検索語と各オプションは図面に保存されない**（セッション内の UI メモリのみ）。Ctrl+R はモーダル置換
- **アプリのユーザ設定（図面外）**: **ファイル** → **ユーザ設定…**。永続化は `logic_cad/ui/app_user_settings.py` の `QSettings`（**Ini 形式**）。起動時に `logic_cad/app/main.py` で `QApplication.setOrganizationName("LogicCAD")` / `setApplicationName("Logic CAD")` を設定しているため、保存先は OS の既定ユーザ設定ディレクトリ配下の `.ini`（例: Windows では `%LOCALAPPDATA%` 系。実際のパスは実行時に `QSettings.fileName()` で確認可能）。クロスヘアは `DiagramView` がビューポート座標でオーバーレイ描画（`none` / `full` / `local`）。**レガシー Ini の `mode=both` は読み込み時に `full` として扱う**（保存はされない）。交点の中空□は Ini キー `crosshair/center_box_side_px`（0＝□なし、十字のみ）。
- メインウィンドウのタイトルバー表示（`Logic CAD vX.Y.Z ...`）: `logic_cad/core/model/constants.py` の `APP_DISPLAY_NAME_WITH_VERSION` を `logic_cad/ui/main_window/document_actions.py` の `build_window_title` が参照して組み立てる。
- UIログウィンドウ: **表示** → **ログ…**。`logic_cad/ui/logging/log_store.py` が `stdout/stderr` をプロセス内でキャプチャし、`logic_cad/ui/panels/log_window_dialog.py` が `QPlainTextEdit` へタイマー間引き（既定 80ms）で反映する。大量出力時の負荷を抑えるため、履歴はリングバッファ（既定 10,000 行）に制限される。

---

## 起動引数（`python -m logic_cad.app.main`）

| 引数 | 効果 |
|------|------|
| **`--debug`** | 起動時に root logger を `DEBUG` に設定し、詳細ログ（ルーティング verbose 含む）を有効化する。 |
| **`--routing-manhattan-only`** | デバッグ用。`LOGIC_CAD_ROUTING_OVG=0` を設定し、固定マンハッタン段のみ試す（OVG マルチを無効化）。 |
| **`--routing-ovg-only`** | デバッグ用。`LOGIC_CAD_ROUTING_FIXED=0` を設定し、OVG マルチのみ試す。 |
| **`--show-routing-bbox`** | デバッグ用。`LOGIC_CAD_SHOW_ROUTING_BBOX=1` を設定し、シーン上に routing 障害物AABB（ベース障害物）を半透明オーバーレイ表示する。 |
| **`--show-connect-bbox`** | デバッグ用。`LOGIC_CAD_SHOW_CONNECT_BBOX=1` を設定し、配線モード中の接続ポート切り欠き（`access_ports`）反映後 AABB を半透明オーバーレイ表示する。 |

`--routing-manhattan-only` と `--routing-ovg-only` は同時に指定できません。
`--show-routing-bbox` と `--show-connect-bbox` は同時指定でき、色分けで比較できます。

---

## 環境変数: ログ

### `LOGIC_CAD_LOG_LEVEL`

Python root logger の閾値です（例: `DEBUG` / `INFO` / `WARN` / `ERROR`）。未設定時は `WARN`。  
また、UI の **表示 → ログ…** のコンボボックスからも実行中に root logger レベルを変更できます（表示フィルタではなく発行閾値の変更）。

**`[logic_cad:toc]`**（`logic_cad/core/services/toc_frame_service.py`）: 目次再生成で **`LD_CONTENTS_AREA` ガイドが無い**ため既定の目次領域 bbox を使うとき、`CONTENTS_*` ブロックの **`LD_CONTENTS_FRAME` 寸法が取れず**セル既定値に落ちるとき、**MTEXT 目次フォールバック**に切り替えたとき、など。

### ルーティング verbose ログ

**量の多いルーティング詳細**（行ごとのバンドル、OVG の no_path / first_hop、escape トレース、`bundle vertical_parallel_diag` など）は、`logic_cad` ロガーが `DEBUG` レベルのとき有効です（`--debug` で有効化）。

OVG の負荷調査向けに、次のログも出力されます（`logic_cad/core/routing/ovg.py`）。

- `ovg_multi attempt ...` : dense モードごとの試行（ノード数、有効 start 数）
- `ovg graph ...` : 構築済みグラフの `nodes` / `edges` / `starts`
- `ovg success ... explored=...` : A* 探索で実際に展開した状態数
- `ovg_multi exhausted ...` : dense を使い切っても解が無いケース

例（Unix シェル）:

```bash
python -m logic_cad.app.main --debug
```

### `LOGIC_CAD_DEBUG_SYMLIB`

`symlib_log` の **`[symlib] …`** 出力を制御します。

- **root logger が `INFO` 以下**のときは、シンボルライブラリ用ログも有効（一般デバッグに含まれる）。
- root logger が `WARN` 以上でも、`LOGIC_CAD_DEBUG_SYMLIB=1` で **`symlib` だけ**を追加有効化できます。

---

## ブロック編集スクラッチ（`create_scratch_with_block_from_main`）

本体から BEDIT 用スクラッチへブロックを複製する際は **`serialize_entity` / `restore_entity_from_payload`** により、到達可能なブロック定義ツリー（`INSERT` 依存）ごとコピーする。`ezdxf.addons.Importer` は [公式どおり XDATA を除去する](https://ezdxf.readthedocs.io/en/stable/addons/importer.html)ためこの経路では使わない（再オープン後に `USER_*` ジオメトリの LD_APP が欠けパッシブ表示になるのを防ぐ）。先に全依存ブロックの空定義を作成してからエンティティを復元し、ネストした `INSERT` が解決できるようにしている。

---

## シンボルライブラリ再読み込み（`reload_symbol_library`）

`logic_cad/core/services/layout_service.reload_symbol_library` は、起動中に `logic_cad/assets/symbol_library.dxf` を現在の `Drawing` へ再度マージする（UI は **テンプレート** → **シンボルライブラリを再読み込み**）。実装モジュールは `layout_service/layout_symbol_library.py`。

`import_symbol_library` を**同一ドキュメントに二度**適用すると、ezdxf `Importer` の既定 `rename=True` により既存ブロック名が衝突し、`BLOCK0` のような**複製ブロック**が増える。再読み込みでは、ライブラリに既に存在するブロック名については対象 `BlockLayout` 内のエンティティを削除してから `Importer.import_entities` で差し替え、`finalize`（INSERT 名解決）の前に `Importer.imported_blocks[name] = name` をシードして、解決時に意図せぬ複製を防ぐ。ソースにしか無い名前は従来どおり `import_block` で追加する。

---

## 図枠テンプレート適用（`apply_frame_template_from_path`）

`logic_cad/core/services/layout_service.apply_frame_template_from_path` は、ユーザーが選んだ DXF（`generate/frame_template.py` と同系の `LD_PAPER_FRAME` / `CONTENTS_*` を想定）から、テンプレ用ブロック定義を `reload_symbol_library` と同様に**中身差し替え**し、各用紙レイアウトで **`LD_PAPER_FRAME` の INSERT を削除**（未タグの旧コピー含む）→ **`LD_CONTENTS_AREA` ガイドの削除** → `import_frame_template(..., path=...)` で再配置 → `regenerate_toc` / `refresh_all_frame_captions`。UI は **テンプレート** → **図枠テンプレートを適用…**。実装モジュールは `layout_service/layout_frame_template.py`。

- 2026-04 更新: `import_frame_template` は template の modelspace をコピーせず、`LD_PAPER_FRAME` / `CONTENTS_*` のブロック定義を取り込んだうえで、用紙レイアウトに `LD_PAPER_FRAME` の INSERT を 1 つだけ配置する。
- 2026-04 更新: 図枠 ATTDEF は `DWG_NO`, `PAGE_NAME`, `PAGE_DESC`, `PAGE_REV`, `PAGE_NUM`, `PAGE_TOTAL` の 6 タグを直接同期する（`{{}}` 展開非依存）。
- 2026-04 更新: DXF 読込は fast-path `ezdxf.readfile` 失敗時に `ezdxf.recover.readfile(errors='ignore')` へフォールバックし、監査エラーは `logic_cad_log("dxf", ...)` へ記録する。

---

## 環境変数: ルーティング計測（プロファイラ）

### `LOGIC_CAD_PERF_ROUTING`

真のとき、`reroute_wires_after_symbol_moves` / `reroute_wires_touching` 内の処理ごとに経過時間を累積します（`routing_perf_add` / `routing_perf_span`）。無効時は **オーバーヘッドほぼ無し**（環境変数の参照と分岐のみ）。

代表的なラベル:

| ラベル | 内容 |
|--------|------|
| `reroute_after_move.index_rebuild_pre` / `_post` | 再配線前後の `IndexStore.rebuild` |
| `reroute.incident.parallel_shift` | 付随配線の平行移動（ポリラインシフトのみ） |
| `reroute.incident.auto_route` | 付随配線のフル自動再探索（`_auto_route_manhattan_interior_points` 等） |
| `reroute.gate.parallel_bundle` | AND/OR 入力束の平行移動まわり |
| `reroute.gate.optimize_bundle` | `optimize_and_or_input_ports`（ゲートごとに加算） |
| `reroute.gate.optimize_failure_index_rebuild` | バンドル失敗時のインデックス再構築 |
| `reroute.gate.crossing_swaps` | 交差スワップ試行 |
| `reroute.bridges` | `recompute_all_bridges_ordered` |

**`optimize_and_or_input_ports` 内訳**（`gate_input.optimize.*` / `gate_input.bundle.*`）も同じ env で有効です。

| ラベル | 内容 |
|--------|------|
| `gate_input.optimize.prepare` | 予約 IN 走査・ログ・バックアップ作成 |
| `gate_input.optimize.assign_ports` | `_assign_gate_input_ports_by_source_order` |
| `gate_input.optimize.index_rebuild_after_assign` | 割当後の `index.rebuild` |
| `gate_input.optimize.post_route_ordered` | `_gate_input_wire_rows_in_order` |
| `gate_input.optimize.crossing_swaps` / `index_rebuild_before_crossing_swaps` | 交差スワップ経路 |
| `gate_input.optimize.bridges_*` | 成功・失敗・割当不能など別々の `recompute_all_bridges_ordered` |
| `gate_input.bundle.setup` | 束ルート開始時の `rebuild`・ソフト障害・スナップショット |
| `gate_input.bundle.order_pick` | 下から/上からの順序を `eval_bundle_order` で比較して選択 |
| `gate_input.bundle.eval_scoring` | 各 `eval_bundle_order` 内の交差・重なり・シンボル衝突スコアリング |
| `gate_input.bundle.first_pass_block` | 本命の `run_pass`（フォールバック含む） |
| `gate_input.bundle.analyze_first_pass` | 交差・重なり診断・クリーンアップ要否 |
| `gate_input.bundle.cleanup_pass` | `gate_cleanup_pass` 時の spread `run_pass` |
| `gate_input.bundle.finalize` | 最終パス取得と診断 |
| `gate_input.bundle.rm_preflight_and_obstacles` | 各行の事前計算＋`build_routing_obstacles`（全 `run_pass` で累積） |
| `gate_input.bundle.rm_preflight.obstacles` | `rm_preflight` のうち障害物組み立て（hard/soft/symbol） |
| `gate_input.bundle.rm_preflight.overlap_segments` | `rm_preflight` のうち既存 wire segment 集約 |
| `gate_input.bundle.rm_preflight.ovg_inputs` | `rm_preflight` のうち OVG 呼び出し入力構築 |
| `gate_input.bundle.rm_route` | `route_manhattan_with_escape`（同上） |
| `gate_input.bundle.rm_apply` | ポリライン確定・`set_wire_points`（同上） |
| `gate_input.bundle.order_pick.candidate.<name>.ok` | 候補順（`bottom_up` / `nearest_src` / `top_down`）ごとの評価成功時間 |
| `gate_input.bundle.order_pick.candidate.<name>.fail` | 候補順評価が失敗（`ValueError`）したケースの評価時間 |

`gate_input.bundle.*` の区間スパンは **直列**（`order_pick` → `first_pass_block` → …）で、かつ `rm_*` は `run_pass` 内の **部分集合**なので、一覧の「total」に全キーを足すと二重計上になります。ボトルネック把握には **`rm_route` と `rm_preflight_and_obstacles`**、および **`order_pick` / `first_pass_block`** の大小を見るとよいです。

### バンドル最適化の実装メモ（性能）

- `gate_input.bundle.order_pick` は候補順（`bottom_up` / `top_down` / `near_first`）の **wire UID + port を含むシグネチャが同一なら評価を再利用**する。  
  さらに `bottom_up` と `nearest_src` の評価差が十分大きい場合は `top_down` をスキップし、近い評価時だけ 3 候補を完全評価する。
- `run_pass` では、束評価中に不変な前処理をキャッシュする。  
  具体的には、非束ワイヤの hard 障害物、シンボル障害物（hard/overlap 判定用）、pair soft 障害物、既存ワイヤセグメントを再利用する。
- `cleanup_pass` は first-pass の交差/重なり/シンボル衝突に関与した wire を優先し、対象行を絞って再探索する。  
  対象外の wire は seed soft obstacle として固定扱いする。
- 改善効果は主に `gate_input.bundle.order_pick` と `gate_input.bundle.rm_preflight_and_obstacles` に現れる。  
  `gate_input.bundle.rm_route` は探索本体なので、前処理削減後も大きい場合は探索プロファイル側の調整を検討する。
- `optimize_and_or_input_ports` では、auto-row を wire 単位に判定し、`dst_port` 不変かつ端点整合と `src/dst` の同一Δが成立する wire は再探索せず平行移動のみ適用する。  
  条件を満たさない wire（入力数変更やポート再割当、端点不一致など）のみ `_route_gate_input_rows` で再探索する。
- `logic_cad/tests/test_routing_perf_test0_translate.py` の計測では、部分並進スキップ導入後に次の改善を確認（環境差あり）。  
  `single_599139dd` は `reroute.gate.optimize_bundle` が約 `1421ms -> 78ms`、`parallel_5symbols` は約 `1141ms -> 690ms`。

`routing_perf_format_lines()` で一覧化できます。`logic_cad/tests/test_routing_perf_test0.py` を `LOGIC_CAD_PERF_ROUTING=1` 付きで `pytest -s` 実行すると、サンプル DXF がある場合に内訳が表示されます。

---

## 環境変数: ルーティングフェーズ（スクリプト・デバッグ）

`apply_routing_env_overrides` が読みます（空・未設定は変更しません）。値は **`0` / `false` / `no` / `off` 以外を真**とみなします。

| 変数 | 対応する `RoutingProfile` フィールド |
|------|----------------------------------------|
| **`LOGIC_CAD_ROUTING_FIXED`** | `use_fixed_manhattan` |
| **`LOGIC_CAD_ROUTING_OVG`** | `use_ovg_multi` |

起動引数 `--routing-manhattan-only` / `--routing-ovg-only` は、上記のいずれかを自動でセットします。

### WIRE「直交を許可」（`allow_orthogonal_cross`）

- WIRE の LD_APP に `allow_orthogonal_cross:1` があると、ルーティングは `RoutingProfile.min_cost_across_wire_obstacle_passes=True` として扱われる（実装名は歴史的経緯で残置）。
- `route_manhattan_ovg_layers`（`logic_cad/core/routing/constrained_router.py`）では **フル障害（他線の太い矩形を含む）ではルートせず**、`obstacles_relaxed`（シンボル硬障害のみ）だけで固定→OVG を試す。初回 `connect_ports` ではまだ XDATA が無いため、プロパティでオンにしたあと再ルートが必要。

---

## テスト用（参考）

| 変数 | 用途 |
|------|------|
| **`LOGIC_CAD_TEST_RENDER_OUT`** | 一部テストでレンダリング出力先の上書きに使います（通常利用は不要）。 |

---

## DXF ヘッダ（Logic CAD が予約する変数）

アプリが図面全体のメタデータに次の **標準 DXF ヘッダ変数** を使います（他用途で上書きしないでください）。

| 変数 | 用途 |
|------|------|
| `$PROJECTNAME` | 図面番号・図枠の `{{DWG_NO}}`（**プロジェクト設定 → 図面プロパティ**） |
| `$USERI1` | 図枠 `{{PAGE_NUM}}` の**開始ページ番号**（先頭用紙のタブ順における表示番号の起点） |
| `$USERI2` | 図枠 `{{PAGE_TOTAL}}` の**総ページ数**。**0 または未設定**のときは、このドキュメントの**用紙レイアウト数**（目次シートを含む `list_paper_layout_names_sorted` と同じ並びの枚数）を使います。 |

`{{PAGE_NUM}}` は `$USERI1` を `s` とし、各用紙をタブ順（目次レイアウトを含む）で 1 始まりの `i` 番目とすると **`s + (i - 1)`** として表示します。桁揃えはしません。

---

## DXF ドキュメントメタデータ（`LD_DOC`）

他 CAD が HEADER の `$ACADVER` などを書き換える可能性があるため、**製品名・アプリ版・ドキュメント形式版・保存時 DXF プロファイル**は **XDATA** に保存する。

### 実装

- コア: `logic_cad/core/model/document_meta.py`
- 定数: `APPID_DOC`（`LD_DOC`）、レイヤ `LAYER_DOC_META` — `logic_cad/core/model/constants.py`
- 保存時スタンプ・新規ドキュメント: `logic_cad/core/dxf/dxf_repository.py`（`apply_document_meta_stamp`）

### ファイル上の見え方（テキスト DXF）

- **APPID テーブル**に `LD_DOC` が登録されることがある。
- **ENTITIES** 内、モデル空間の **POINT**（レイヤ `LD_DOC_META`、座標およそ `-1e6`, `-1e6` mm）に **XDATA** が付く。
- グループ **`1001`** = アプリ名 `LD_DOC` のあと、**`1000`** 文字列がキー値形式（`key:value`、保存時はキー名でソート）で並ぶ。
  - `creator` … 製品名（例: `Logic CAD`）
  - `app_version` … `logic_cad` パッケージの `__version__`
  - `doc_format` … 将来の互換・移行用（`DOC_FORMAT_VERSION`、現状 `"1"`）
  - `dxf_profile` … 保存時プロファイル文字列（現状 `"R2010"`）

テキストエディタで探すなら **`LD_DOC`** または **`Logic CAD`** の検索が手早い。

### API

- 読み取り: `read_document_meta(doc)`
- 書き込み（通常は `saveas` / `new_document` 経由）: `apply_document_meta_stamp(doc, dxf_profile="R2010")`

## レイヤ線設定（線太・色）

- **UI**: **プロジェクト設定** → **レイヤ線設定…**（旧: 表示メニューにあった項目を移設）。
- ダイアログ: [`logic_cad/ui/layer_lineweight_dialog.py`](../logic_cad/ui/layer_lineweight_dialog.py) — 線太に加え、レイヤ色を **真色**（`layer.dxf.true_color`）または **索引色**（`layer.dxf.color` の ACI 1〜255、`true_color` は解除）のどちらかで編集する。書き込みヘルパは [`dxf_display_color`](../logic_cad/ui/dxf_display_color.py) の `apply_qcolor_to_dxf_layer` / `apply_aci_to_dxf_layer`。
- 色ピッカー実装メモ: `_LayerColorSwatchButton._pick_color()` は static `QColorDialog.getColor(..., self, ...)` を使わず、`QColorDialog` インスタンスをトップレベル親（`self.window()`）で生成する。色スウォッチボタン自身の `background-color` スタイルを親にすると、色ダイアログの見た目が選択色に引きずられる環境があるため。
- キャンバスでの配線・ユーザ図形の色: [`logic_cad/ui/dxf_display_color.py`](../logic_cad/ui/dxf_display_color.py) の `entity_stroke_qcolor` がエンティティの BYLAYER / 真色 / ACI を `QColor` に解決する。
- [`ensure_standard_layers`](../logic_cad/core/dxf/dxf_repository.py) は **標準レイヤを初めて `doc.layers` に追加するときだけ** デフォルト ACI を付与する。既存レイヤの `color` / `true_color` は読み込み・保存のたびに上書きしない（ユーザー設定の永続化）。
- チェックボックス視認性: `QCheckBox::indicator` は OS テーマ依存にせず [`logic_cad/ui/styles/app_stylesheet.py`](../logic_cad/ui/styles/app_stylesheet.py) で明示スタイルする。チェックON/OFFアイコンは [`logic_cad/ui/styles/assets/checkbox_checked.svg`](../logic_cad/ui/styles/assets/checkbox_checked.svg) / [`logic_cad/ui/styles/assets/checkbox_unchecked.svg`](../logic_cad/ui/styles/assets/checkbox_unchecked.svg) を使用。
- 目視確認ポイント（チェックボックス修正時）: プロパティ、検索ダイアログ、PDF出力ダイアログで ON/OFF/disabled が背景色とマークで判別できることを確認する。

### 線種名の定数（`constants.py`）

- **配線（Logic / Value ユニット）**: `LINETYPE_LOGIC` と `LINETYPE_VALUE` のみを `LAYER_WIRE_*`・WIRE 系に使う。
- **ユーザ補助（USER_LINE / USER_CIRCLE / USER_CLOUD / USER_TEXT）**: `LINETYPE_CONTINUOUS` / `LINETYPE_DASH` / `LINETYPE_CENTER` を使う。Logic 側の線種を将来変更しても（例: Logic を破線に）紙面スケッチの既定が誤って連動しないよう、ユーザ系コードから `LINETYPE_LOGIC` を参照しない。

## 関連ドキュメント

- ユーザーマニュアルの起動例・図枠まわりのログ言及: [`user_manual.md`](user_template_manual.md)（§1・§4-1）

## インアプリマニュアル（Markdown ビューワ）

- **UI**: **表示** → **マニュアル…**。左に `docs` 直下の `*.md` 一覧、右に HTML プレビュー（`QTextBrowser`）。実装の中心は [`logic_cad/ui/panels/manual_dialog.py`](../logic_cad/ui/panels/manual_dialog.py)。
- **開発時のパス**: リポジトリ直下の `docs/`。解決は [`logic_cad/docs_path.py`](../logic_cad/docs_path.py) の `docs_directory()`（`logic_cad` パッケージの親ディレクトリ直下の `docs`）。
- **PyInstaller**: リポジトリの `docs` フォルダを **`datas` でバンドル内の `docs` 名で同梱**する。実行時は `sys._MEIPASS / "docs"` を参照する。サンプルは [`scripts/logic_cad.spec`](../scripts/logic_cad.spec)。リポジトリルートで `pyinstaller --noconfirm scripts/logic_cad.spec` のようにビルドする。`datas` を忘れるとマニュアル一覧が空になる。
- **相対リンク**: プレビューは `QTextDocument.setBaseUrl`（`docs` ディレクトリ基準）と `anchorClicked` で、`docs` 直下の他 `*.md` はアプリ内で開き、`http`/`https` はブラウザ、`../logic_cad/...` などは OS の既定アプリへ委譲する。
- **除外**: `TODO.md` は一覧から除外（[`manual_dialog.EXCLUDED_MARKDOWN_NAMES`](../logic_cad/ui/panels/manual_dialog.py)）。

---

## キャンバス雲描画（PySide6）メモ

- `LWPOLYLINE bulge` のキャンバステッセレーションは `logic_cad/ui/bulge_path.py` の `append_bulge_arc_to_path` を正本として扱う。
- `UserCloudItem`（確定済み雲）と `DiagramScene`（雲プレビュー）は同ヘルパを必ず経由し、角度補間ロジックを重複実装しない。
- 掃引角は絶対角差ではなく `bulge` 由来の符号付き角度（`4 * atan(bulge)`）で扱い、象限跨ぎ時の角度ラップでスパイラル化しないようにする。
- テッセレーション終点は弦終点へスナップする実装を維持し、オフセットや象限に依存した終点ドリフトを避ける。

### USER_CLOUD のピッチ（LD_APP）

- `cloud_seg`: `revcloud.points` の `segment_length`（最後に適用した値）。
- `cloud_path_0`, `cloud_path_1`, …: ガイド頂点列の JSON（長い場合は 200 文字程度でチャンク分割）。実装は `logic_cad/core/model/cloud_guide_xdata.py`。
- 旧データでガイド無しの場合、プロパティからピッチ適用時に Douglas–Peucker で外形を推定してから上記を書き込む（`logic_cad/core/geometry/polyline_simplify.py`）。

---

## ユーザ操作マニュアル（`user_operation_manual.md`）

コードベース調査に基づき、新規作成。**日常的なUI操作、ショートカット、ページ管理、注釈ツール、配線フロー、トラブルシューティング**を中心にまとめ、**ユーザからの問い合わせの大部分をこの1ファイルで完結**できるように設計しました。

- `user_manual.md` はテンプレート作成・DXF仕様詳細向け
- 本ファイルは **エンドユーザー操作マニュアル** として `docs/` に追加（インアプリマニュアルに自動収録）
- 改善点（例: スクリーンショット追加、動画デモ連携）は今後検討。TODOとしてコード内に残さない（ドキュメントはユーザ明示依頼時のみ積極変更）

関連: `logic_cad/ui/panels/manual_dialog.py`, `logic_cad/ui/main_window/window.py`, `logic_cad/ui/panels/property_panel.py`, 各種ツールボタン・シーン実装。

---

## 文字解決一括化（Unified Text Layout）

`TEXT` / `ATTDEF` / `ATTRIB` / `MTEXT` / `USER_TEXT` / TOC fallback MTEXT は、`logic_cad/core/text/layout_resolver.py` の正規化を通して扱う。

- `normalize_dxf_text_entity(...)`  
  DXFエンティティの文字列、高さ（`height` / `char_height`）、アンカー（`get_placement` / `insert` / `attachment_point`）、回転、幅係数を `NormalizedTextLayout` に統一する。
- `build_single_line_layout(...)`  
  DXFエンティティではないUI生成テキスト（`USER_TEXT` など）を同じ構造へ揃える。
- `ui_font_family_chain(...)` / `resolve_pdf_font_face_for_ui_family_chain(...)` / `apply_render_context_fonts_for_pdf_like_ui(...)`  
  UIの family chain は **（プロジェクト優先フォントがあればそれ）→ DXF style 由来 → `font_family_candidates` 順 → `sans-serif`**。プロジェクト優先は **プロジェクト設定 → 優先フォント…** で選び、ドキュメントアンカー POINT の ``LD_DOC`` XDATA キー `preferred_font_family` に保存する（未設定・空＝従来どおり DXF 優先）。PDF（matplotlib 経路）は **TEXTSTYLE ごと**に同じチェーンで `FontFace` を解決し、`RenderContext.fonts` を上書きする。スタイル単位の優先ファミリは `font_family_preferred_for_named_style` / `font_family_preferred_for_style_table_key` で UI と揃える。既定スタイルのみ必要な場合は `preferred_pdf_font_face()`（内部で上記チェーンのデフォルト起点を使用）。
- `decode_dxf_unicode_escapes(...)`  
  DXF の特殊 Unicode エスケープ（例: `\U+3042`）を UI/PDF で共通解釈する。`normalize_newlines(...)` は内部でこの関数を通す。PDF 側は `pdf_export_service._PdfExportFrontend` が描画直前にテキスト系エンティティをクローンしてこのデコードを適用し、元の DXF エンティティを変更しない。

設計意図:

- 描画実装（Qt / matplotlib）は分離しても、**文字意味解釈は1か所**に集約する。
- 個別経路の経験則（例: 経路ごとの文字サイズ係数）を減らし、DXF意味準拠を優先する。
- 回帰評価は主に幾何（高さmm・幅mm・アンカー位置）で行い、環境依存のフォント見た目差は二次評価にする。

既知制約:

- MTEXTの全仕様（flow方向、段組、リッチ書式）をUIで完全再現するものではない。
- フォント実体はOS依存のため、同じファミリ名でも環境ごとに厳密一致しないことがある。
- PDF の `find_best_match` と Qt の `QFont` は同一チェーンでも実ファイルの選び方が完全一致しない場合がある（意図は「同じ優先順・同じスタイル別方針」）。

---

## ATTDEF中央揃えのUIアンカー解釈（2026-04）

`ATTDEF` / `TEXT` / `ATTRIB` の単一行テキストは、`normalize_dxf_text_entity()` で「DXF生値」と「UI描画向け実効値」を分離する。

- 生値: `halign` / `valign` / `rotation_deg` / `width_factor` はDXF値を保持する。
- 実効値: `render_halign` / `render_valign` / `render_rotation_deg` / `render_width_factor` / `render_fit_length_mm` / `render_fit_mode` をUI描画で使用する。

アンカー算出と特殊整列の規則:

1. `halign == 0` かつ `valign == 0`（左・ベースライン）は `insert` をアンカーにする。  
2. それ以外は `align_point` 優先、無ければ `get_placement()`、最後に `insert`。  
3. `halign == 4`（MIDDLE）は UI では **center-middle** として扱い、`render_halign=1` / `render_valign=2` に正規化する。  
4. `halign == 3`（ALIGNED）/ `halign == 5`（FIT）は、開始点 `insert` をアンカーに固定し、`align_point`（または `get_placement()` の p2）までの基線長を `render_fit_length_mm` に格納する。`ALIGNED` は `render_fit_mode=\"aligned\"`、`FIT` は `render_fit_mode=\"fit\"`。  

描画側（`logic_cad/ui/block_paint.py`）は上記 `render_*` を使い、`paint_text_path_mm()` と `text_path_bounds_item_local()` の両方で同じ規則を適用する。これにより BricsCAD 由来の `halign=4`/`align_point` 付き ATTDEF でも表示位置と選択境界の不一致が起きにくくなる。

設計意図:

- DXF/PDFが正しいのにUIだけ位置ずれするケースを、TEXT特殊整列（ALIGNED/MIDDLE/FIT）を含めて防ぐ。
- 文字描画と境界計算のロジック差をなくし、ヒットテストや外接矩形の回帰を抑える。

関連テスト:

- `logic_cad/tests/test_text_layout_resolver.py`
- `logic_cad/tests/test_attdef_placement_anchor.py`
- `logic_cad/tests/test_passive_dxf_primitives.py`

---

## ブロック編集: ATTDEF／ポートの開幕スナップ抑止

`logic_cad/ui/symbol_block_editor/scene.py` で、`_rebuild` によるプログラム配置では `AttdefEditItem` の `_programmatic_pos_depth` および `PortMarkerItem.place_at_dxf_mm` が効き、`setPos` がグリッドに丸められない。インタラクティブな移動時のみ従来どおり `itemChange` でスナップする。`_commit_attdef_moves` / `_commit_port_moves` は `_moved` / `_pm_moved` が立っているアイテムだけ DXF に書き戻す。

そのうえで「フラグだけ誤って立つ」場合があるため、左クリック押下時に `_snapshot_selection_drag_starts` が記録したシーン座標から実際に動いたアイテムだけコミットする（`_item_scene_dragged_since_press`）。

別要素を動かしたときのマウス解放で、ピッチとの丸め差だけで ATTDEF／ポートがずれるのを防ぐ。

関連テスト: `logic_cad/tests/test_block_edit.py`（`test_block_edit_refresh_keeps_off_grid_attdef_scene_pos` / `test_block_edit_refresh_keeps_off_grid_port_scene_pos`）

---

## ブロック編集: 新規 ATTDEF 既定と「本体へ適用」後の ATTRIB 同期

- **`add_attdef_to_block`**（`logic_cad/core/services/block_edit_helpers.py`）で追加する ATTDEF は、左寄せ **`halign = 0`** と **`align_point`（`insert` と同じ 3D 点）**を明示する。新規配置シンボルの ATTRIB が `dxfattribs_for_attrib_from_attdef` 経由でも整列情報欠落しにくくするため。
- **「本体へ適用」直後**（`logic_cad/ui/panels/block_edit_panel.py`）: 確認なしで、このセッションのブロック名を参照する **INSERT の ATTRIB 幾何**を ATTDEF に合わせて `sync_insert_attrib_geometry_for_block_name` で同期する（`logic_cad/core/dxf/attrib_geometry_sync.py`）。**`text` と `invisible` は変更しない**。

関連テスト: `logic_cad/tests/test_block_edit.py`（`test_add_attdef_to_block_sets_halign_and_align_point` / `test_sync_insert_attrib_geometry_for_block_name_only_matching_inserts`）

---

## シンボルクリップボード（プロセス間コピー）

編集メニューのコピー／貼り付けは、`MainWindow._symbol_clipboard` に加え **`QClipboard`** に独自 MIME `application/x-logic-cad-symbol-clipboard`（UTF-8 JSON、実装は `logic_cad/core/symbol_clipboard_codec.py`）を書き込む。別プロセスの logic_cad でも、同じブロック定義が貼り付け先 DXF に存在すれば貼り付け可能。ブロック未定義の場合は従来どおりエラーになる。

---

## PAGE_REF の PAGE_NAME / PAGE_DESC 表示

- `PAGE_REF` は XDATA キー `show_page_name` / `show_page_desc`（`"1"` のとき ON）で、`PAGE_FROM` / `PAGE_TO` **ブロック定義**内の **`PAGE_NAME` / `PAGE_DESC` ATTDEF** の表示可否をそれぞれ切り替える。追加する ATTDEF のタグ名は **`PAGE_NAME` と `PAGE_DESC`**（ブロック名の `PAGE_FROM` / `PAGE_TO` を ATTDEF タグにする必要はない）。
- 新規配置時のデフォルトは両方 OFF（`"0"`）で、`SYM` は従来どおり常に非表示 ATTRIB として同期する。
- `refresh_page_ref_syms_on_layout()` は `SYM` の再採番に加え、リンク先レイアウト名・`page_desc` を `PAGE_NAME` / `PAGE_DESC` ATTRIB に同期する（ATTDEF が無い場合は no-op）。

---

## WIRE矢印の線種固定（2026-04）

- `WireArrowItem`（`logic_cad/ui/items/wire_arrow_item.py`）の矢印描画は、`WIRE` エンティティの `linetype` に関係なく常に `Qt.PenStyle.SolidLine` で描画する。
- DXF 側の `WIRE_ARROW` には従来どおり親 `WIRE` の `linetype` を同期して保持する（`sync_wire_arrow_dxf`）。データ整合性は維持しつつ、UI表示のみ矢印を実線固定にする設計。
- AND/OR の入力スタブ矢印は `GATE_INPUT_STUB_ARROW`（レイアウト直下 `LWPOLYLINE` / `LD_SYMBOL`）として `SymbolService.sync_gate_stub_arrows_dxf` が同期し、PDF／素の DXF でも `WIRE` の `WIRE_ARROW` と同様に見える。Qt 側は `WireArrowItem` で当該 LW を描画し、実線は `WireArrowItem` と同じく固定。

---

## INSERT ATTRIB と ATTDEF の幾何（Qt vs matplotlib）（2026-05）

Qt はブロック内 **ATTDEF**＋`normalize_dxf_text_entity()` でラベル位置を決めるが、ezdxf の matplotlib 経路は **ATTRIB** 実体の DXF 整列情報のまま描画する。食い違うと PDF だけズレうる。

- 共通: `logic_cad/core/dxf/attrib_geometry_sync.py`（`apply_attdef_text_geometry_to_attrib` / `sync_paper_layout_insert_attrib_geometry_from_attdefs` は **任意** の修復用。ATTDEF に `align_point` が無いときは ATTRIB 側の `align_point` を触らない ― *例外として* `readfile` の WCS→局所復帰で、ATTDEF に無い `align_point` が子に残っているときは `discard` する）
- **新規** ATTRIB: `dxfattribs_for_attrib_from_attdef()` を `SymbolService._add_insert_attrib` と `page_ref._upsert_insert_attrib_from_attdef` で利用（`add_auto_attribs` 失敗時など）
- **記号配置直後（2026-05）**: `SymbolService.place_symbol` は **`LD_PORT_*` 以外のすべての ATTDEF** について子 ATTRIB を作成し（既定文字は ATTDEF）、続けて `sync_insert_attrib_geometry_from_attdefs` を1回呼ぶ。SYM のみを付けていた旧挙動では **SYM のないブロック（例: DISC_FIELD の LABEL だけ）** が原点付き欠落になりうる。
- **既存** ATTRIB（PAGE_REF の refresh 経由）: `_upsert_insert_attrib_from_attdef` は **`text` / `invisible` のみ**更新し、幾何を ATTDEF に毎回追従させない（定義側の退化座標で refresh が悪化し続けるのを避ける）。定義を直したあと位置を合わせるには `sync_insert_attrib_geometry_from_attdefs` か、ブロック適用後の `ensure_cross_page_reference_blocks` 内の退化 ATTDEF 修復＋同期に任せる
- **PDF エクスポート（子 ATTRIB の WCS）**: ezdxf の matplotlib フロントは `virtual_entities()` のあと `insert.attribs` を **INSERT 行列なし**で描く。そのため子 ATTRIB の `insert`／`align_point` は **紙レイアウト WCS** である必要がある。`export_paper_layouts_to_pdf` は各ページの `draw_layout` 直前に `paper_layout_attrib_wcs_bake_for_pdf_session`（内部で snapshot → bake → 描画後 restore）を使い、**ブロック局所のまま**と判定できたときだけ ATTDEF 幾何を `Insert.matrix44()` で焼き、ライブ DXF は復元する。既に期待 WCS に近い座標（CAD 側で焼かれたケース）は距離閾値でスキップし二重変換を避ける（`PDF_ATTRIB_POSITION_EQ_TOL_MM`）。
- **DXF ファイル保存／読込（外部 CAD と同じレイアウト座標）**: `logic_cad/core/dxf/dxf_repository.saveas` は `doc.saveas` の直前に PDF と同種の bake を行いファイルへ **子 ATTRIB をレイアウト WCS** で書くが、続けてスナップショット復元により **インメモリはブロック局所のまま**。`readfile` は読込後に `revert_all_paper_layout_attrib_inserts_from_wcs_after_load` を掛け、再び ATTDEF と揃えた **局所**へ戻す（旧ファイルの局所要素はヒューリスティクで変更しない）。

### ユーザー向け: PAGE_REF の PAGE_NAME / PAGE_DESC が枠外／原点付近になるとき

- **シンボルライブラリの再読込**: プロジェクトメニュー等から **シンボルライブラリ再読込**（`reload_symbol_library`）を実行すると、`PAGE_FROM` / `PAGE_TO` のブロック定義がバンドル版に近づき、`PAGE_NAME` / `PAGE_DESC` の ATTDEF 位置もライブラリ準拠になりやすい。
- **ブロックエディタ**: 左の「ブロック」から `PAGE_FROM` または `PAGE_TO` を開き、`PAGE_NAME` / `PAGE_DESC` の **ATTDEF** の挿入点を枠内の意図した位置へ移動する（原点 `(0,0)` のままにしない）。
- **自動修復**: `ensure_cross_page_reference_blocks` 実行時、`PAGE_NAME` / `PAGE_DESC` の ATTDEF 挿入点が原点付近に退化している場合は、ビルトインと同じ座標・字高・水平整列へ書き換え、既存の PAGE_REF INSERT に対して **一度** `sync_insert_attrib_geometry_from_attdefs` 相当の同期を行う。
- **任意の一括幾何同期**: 全レイアウトへの `sync_paper_layout_insert_attrib_geometry_from_attdefs` 等の一括同期は行わない（整合済みの ATTRIB を壊しうるため）。必要ならスクリプトや手動で呼ぶ（上記の **PDF 用 bake／restore** はエクスポート専用で、永続データを変えない）。

関連テスト: `logic_cad/tests/test_attrib_geometry_sync.py` / `logic_cad/tests/test_symbol_place_attrib_geometry.py`

---

## PDF エクスポート: HATCH の `pattern.lines` と Undo（2026-05）

- **症状**: 稀に matplotlib 経路で ``TypeError: object of type 'NoneType' has no len``。ezdxf の `draw_hatch_pattern` が ``pattern is not None`` かつ ``pattern.lines is None`` を想定していないため。
- **対策**: `logic_cad/core/services/pdf_export_service.py` の `_PdfExportFrontend.draw_hatch_pattern` で `lines` を検証してから `super()` に委譲。
- **観察**: シンボル削除→Undo 後に PDF が通ることがある。Undo の `restore_entity_from_payload` でエンティティが作り直され、ezdxf 上の HATCH 内部状態が整合する場合がある（論理内容は同じでもオブジェクト状態が変わりうる）。
- **TODO**: INSERT の復元経路では `add_auto_attribs` のみで ATTRIB が作られ **`align_point` が欠ける**ことがあるため、復元直後に当該 `INSERT` へ `sync_insert_attrib_geometry_from_attdefs` を掛ける案を検討（別タスク）。
- **調査用**: `uv run python scripts/list_pattern_hatches.py drawing.dxf`（ブロック定義内の HATCH も列挙。`risky_lines_none=True` が疑わしい）。

関連テスト: `logic_cad/tests/test_pdf_export.py`（`test_pdf_frontend_draw_hatch_pattern_skips_when_pattern_lines_is_none`）

---

## PDF: PAGE_REF の SYM と PAGE_NAME / PAGE_DESC（2026-05）

- **DXF**: `refresh_page_ref_syms_on_layout` / `place_page_link` は **PAGE_REF** の **SYM** を常に可視（`invisible=0`）。**PAGE_NAME / PAGE_DESC** は `show_page_name` / `show_target_info` 等に従い `visible` 切替。旧ドキュメントで SYM が非表示の場合は PDF clone 側の `_maybe_unhide_page_like_sym_attrib_for_pdf` が吸収。
- **Qt**: `SymbolItem` が PAGE_REF / INPAGE_REF で SYM ラベルを強制表示。
- **PDF**: [`pdf_export_service._maybe_unhide_page_like_sym_attrib_for_pdf`](f:/python_programs/logic_cad/logic_cad/core/services/pdf_export_service.py) が **export 用 clone のみ** `SYM` を `invisible=0`（親 INSERT が `PAGE_REF` / `INPAGE_REF` のとき）。**PAGE_NAME / PAGE_DESC は clone ではいじらない**（チェックオン時だけ従来どおり描画）。
- **幾何**: ATTRIB の `align_point` 欠落対策は `_normalize_text_anchor_for_pdf_clone`（`simplified_text_chunks` の `NoneType has no len` 回避）。

関連テスト: `logic_cad/tests/test_pdf_export.py`（`test_export_pdf_page_ref_invisible_sym_writes_file` / `test_export_symbol_library_pdf_nonzero_size`）

---

## DXF 永続レイヤーと `layout_service` の依存（Phase 1, 2026-05）

- **問題**: `dxf_repository` が `layout_service` を関数内 import しており、`layout_service` が同じモジュールの `ensure_standard_layers` / `load_dxf_with_recover` を参照しているため初期化順の問題を避ける必要があった。
- **対策**: ``LD_CONTENTS_AREA`` の紙レイアウト側ストリップを `logic_cad/core/paper_layout_strip.py` に、A4 用紙＋ VIEWPORT／layer0 デコイ除去まわりを `logic_cad/core/paper_layout_configure.py` に分離。いずれも `dxf_repository` および `paper_layout_access` 以外の上流サービスに依存しない。
- **結果**: `dxf_repository.saveas` / `readfile` はトップレベル import のみ。**`configure_paper_layout_a4_landscape` は `paper_layout_configure` が正本**、`layout_service` はそこから再エクスポートして既存テスト／呼び出し元を維持。

