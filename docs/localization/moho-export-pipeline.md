# Một tài liệu Moho trở thành SVG như thế nào

> Bản dịch tiếng Việt của `docs/moho-export-pipeline.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Tài liệu này giải thích **logic xử lý** của `moho2svg.py`: công đoạn nào tiêu
thụ trường nào, quyết định được đưa ra theo thứ tự nào, và các mảnh của một tài
liệu Moho kết hợp thành đầu ra SVG ra sao.

Nó là tài liệu đồng hành của hai tài liệu khác, và cố ý không lặp lại bất kỳ
tài liệu nào:

| Tài liệu | Trả lời |
|---|---|
| `docs/moho-project-file-format.md` | Trong file có *cái gì* — mọi trường, giá trị của nó, nó có được dùng không. |
| **file này** | Các trường đó được tiêu thụ *như thế nào*, và theo thứ tự nào. |
| Docstring của module trong `moho2svg.py` | *Vì sao* mỗi công thức/hằng số là như vậy, và bằng chứng nào hỗ trợ nó. |

Mọi class, hàm và thuộc tính được nêu tên dưới đây đều tồn tại trong
`moho2svg.py`. Khi một công thức ở đây chỉ được tóm tắt, phần docstring của
module đã suy ra nó sẽ được nêu tên để bạn đến thẳng được chỗ đó.

---

## 1. Tổng quan: luồng dữ liệu

Có hai điểm vào, và chúng dùng chung mọi công đoạn phía dưới:

- `Exporter.export_layer(...)` — một vector layer thành một SVG đứng riêng
  (CLI `--layer`, `--all`).
- `Exporter.export_document(...)` — toàn bộ cây layer thành một SVG
  (CLI `--combined`).

```
                      .mohoproj / .animeproj  (plain JSON)
                                  |
                        load_document(path)                    [CLI]
                                  |
                        Document.from_raw(raw)                 LOAD TIME
                                  |                            (frame-independent)
              +-------------------+-------------------+
              |                                       |
      StyleTable.build(raw["styles"])          Layer._build  (recursive)
              |                                       |
              |                           +-----------+-----------+
              |                           |                       |
              |                     Mesh._build             Skeleton._build
              |                           |
              |              +------------+------------+
              |              |            |            |
              |       MeshPoint._build  Curve._build  Shape._build
              |                                         |
              +---------> ResolvedStyle.resolve <-------+
                          (style inheritance is
                           resolved ONCE, here)
                                  |
                    Document._resolve_patch_layers()
                    (PatchLayer borrows its target's mesh)
                                  |
        ==========================|==========================  frame boundary
                                  |
                        Exporter.export_document(frame)         RENDER TIME
                                  |                             (per frame)
                        emit()  -- walks the tree
                                  |
        +-------------------------+-------------------------+
        |                         |                         |
  _active_smart_bones      build_deform_chain          _mask_sources
  (which dials are on)     (MatrixStep / SkinStep)     (masking==2 siblings)
        |                         |                         |
        |                 _deformed_pixel_mapper            |
        |                 (uses Skinner.deform)             |
        |                         |                         |
        +----------> _render_mesh(mesh, to_px, frame) <-----+
                                  |
                    _curve_geometries(mesh, frame)
                    (BezierReconstructor -> CurveGeometry)
                                  |
                    ShapeGroupRenderer.render()
                                  |
                    per shape: build_path_d
                               (PathTracer re-traces edges)
                               + TaperedStrokeOutliner
                               | or BrushStampOutliner
                                  |
                    _flush()  -- boolean groups close here
                                  |
                          Exporter._wrap()
                       (<svg>, viewBox, <defs>)
                                  |
                              SVG text
```

**Ranh giới frame** ở giữa là điều đáng nhớ nhất. Mọi thứ phía trên nó xảy ra
một lần cho mỗi lần tải file và không bao giờ phụ thuộc số frame. Mọi thứ phía
dưới nó được làm lại cho từng `--frame N`.

Điều **không** có trong pipeline cũng quan trọng không kém: không có công đoạn
z-sorting, không có công đoạn layer-effect, và không có công đoạn camera. Thứ
tự vẽ đơn giản là thứ tự tài liệu, và các trường bị bỏ qua được liệt kê trong
`moho-project-file-format.md` § 13 bị bỏ qua *bằng cách vắng mặt* — không code
nào đọc chúng.

---

## 2. Đồ thị đối tượng: cái gì trỏ vào cái gì

Mô hình tài liệu là một tập **accessor mỏng trên JSON đã parse thô**. Hầu như
mọi thuộc tính là một dòng `self._raw.get(...)`; không có gì bị sao chép. Điều
này quan trọng vì hai lý do: bộ nhớ (một tài liệu 55 MB không bị nhân đôi), và
bộ cache định danh của `Channel.of()` (xem [§ 5.1](#51-channelof-và-bộ-cache-định-danh)).

### 2.1 Chứa đựng theo cấu trúc

```
Document
  .styles ....... StyleTable  (indexed by BOTH uuid and name)
  .layers ....... [Layer]                     <- root layers, draw order
                    |
                    +-- .children ... [Layer]   <- recursive
                    +-- .mesh ....... Mesh?
                    |                   +-- .points .. [MeshPoint]
                    |                   +-- .curves .. [Curve]
                    |                   |                +-- .points .. [CurvePoint]
                    |                   +-- .shapes .. [Shape]
                    |                                    +-- .edges ... [Edge]
                    |                                    +-- .style ... ResolvedStyle
                    +-- .skeleton ... Skeleton?
                                        +-- .bones .. [Bone]
```

### 2.2 Các khóa tham chiếu ("foreign keys")

Đây là các tham chiếu chéo làm định dạng trở thành một đồ thị thay vì một cây.
Tra chúng sai là nguồn phổ biến nhất của đầu ra sai một cách thầm lặng.

| Từ | Trường | Đến | Được giải quyết bởi |
|---|---|---|---|
| `Edge` | `curve` | chỉ số vào `mesh.curves` | `PathTracer.trace`, `_point_widths` |
| `Edge` | `segment` | chỉ số vào `curve.points` / danh sách segment của curve đó | như trên |
| `CurvePoint` | `point` (`point_index`) | chỉ số vào `mesh.points` | `CurveGeometry.build`, `_point_widths` |
| `MeshPoint` | `curves` | các chỉ số trỏ ngược vào `mesh.curves` | **không dùng** — ánh xạ ngược được dựng lại từ `curves` thay vì dùng nó |
| shape / style của shape | `inherited_style_uuid` / `_name`, `inherited_style2_*` | một mục của `doc.styles` | `ResolvedStyle.resolve` qua `StyleTable.get` |
| `Layer` | `parent_bone` | chỉ số vào `skeleton.bones` của `BoneLayer` bao quanh | `build_deform_chain` → `SkinStep.bound_bone_index` |
| `Layer` | `flexi_bone_subset` | các **chỉ số** vào `skeleton.bones` nối bằng `"\|"` | `Layer.flexi_bone_subset` → `Skinner.deform` |
| `Bone` | `parent` | chỉ số vào cùng `skeleton.bones` | `Skeleton.world_matrices` |
| `PatchLayer` | `target_layer_uuid` | `Layer.uuid` của một layer khác, ở bất kỳ đâu trong tài liệu | `Document._resolve_patch_layers` |
| `SwitchLayer` | `switch_keys` (giá trị) | **tên** một layer con (một chuỗi, không phải chỉ số) | `Layer.switch_active_child` |
| channel | `actions[].name` | tên một action trong registry `actions` của một `BoneLayer` tổ tiên nào đó | `Channel.eval` ↔ `Exporter._active_smart_bones` |

Hai mục trong đó xứng đáng được cảnh báo.

**`Edge` là một tập, không phải một chuỗi.** `edges` (các mảng song song
`curve` / `segment` / `flag`) *không* phải một bước duyệt theo thứ tự danh
sách, và `flag` *không* phải một bit hướng đáng tin. Vì vậy `PathTracer` bỏ qua
cả thứ tự lẫn `flag`, và truy lại đường viền như một đồ thị vô hướng khóa theo
các tọa độ đầu mút đã làm tròn. Xem
[§ 6.2](#62-pathtracer-dựng-lại-thứ-tự-duyệt).

**`switch_keys` có thể lỗi thời.** Nó lưu một *tên*, nên đổi tên một layer con
làm hỏng tham chiếu. `Layer.switch_active_child` rơi về layer con **đầu tiên**
thay vì vẽ không gì cả, khớp với điều Moho tự làm (đã xác nhận trên một tài
liệu thật nơi một switch "Mouth" đặt tên `"Layer 2"` là đang hoạt động trong
khi layer con duy nhất của nó tên là `"Closed"`).

### 2.3 Hai phép viết lại lúc tải

`Document.from_raw` không giao lại cây nguyên vẹn. Hai phép chuẩn hóa xảy ra
trước, và cả hai đều tồn tại để không công đoạn nào phía sau cần một trường
hợp đặc biệt:

1. **`TextLayer` nhận một layer con được tổng hợp.** `Layer._build` biến đối
   tượng `mesh_layer` lồng bên trong một `TextLayer` thành một `MeshLayer` con
   thông thường (đặt tên `<layer>_text` nếu nó không có tên riêng). Sau đó,
   không gì ở hạ nguồn đối xử đặc biệt với `TextLayer` nữa.
2. **`PatchLayer` mượn mesh của target.** `Document._resolve_patch_layers`
   chạy *sau khi* toàn bộ cây tồn tại, vì một target có thể ở bất kỳ đâu trong
   tài liệu. Nó sao chép bốn thứ từ target sang patch — `mesh`, `transform`,
   `parent_bone`, `flexi_bone_subset`, và `origin` — và cố ý **vứt bỏ**
   transform/binding riêng của patch. Vòng lặp lặp lại cho đến khi không có gì
   mới được giải quyết, nên một patch mà target của chính nó cũng là một patch
   vẫn hoạt động. Một patch không bao giờ giải quyết được giữ `mesh = None`,
   điều mà mọi công đoạn phía sau đã coi là "vẽ không gì cả".

   Patch và target của nó kết thúc bằng việc dùng chung đúng các đối tượng
   Python `Mesh`/`Shape` (không phải bản sao) — `layer.mesh = target.mesh`.
   Điều đó quan trọng ở lúc render: một patch chỉ vẽ **phần tô** của target,
   không bao giờ vẽ nét viền của nó, đã xác nhận trực tiếp với ứng dụng Moho
   trên hai điểm được chọn để loại trừ một biến gây nhiễu (`masking == 2` và
   `masking == 0`, đều là patch, không cái nào hiện nét viền trong khi target
   của chúng thì có — xem
   [§ 7.6](#76-patchlayer-bỏ-nét-viền-của-chính-nó-không-chỉ-transform)).
   Vì các đối tượng được dùng chung, việc này không thể làm bằng cách lật
   `Shape.has_outline` (như thế cũng làm câm lặng lượt render độc lập, riêng
   của chính target) — nó là một cờ ở lúc render.

`Layer.is_container` được theo dõi tách khỏi việc `children` có rỗng hay không,
chính xác là để giữ hai trường hợp này tách rời:

| Trường hợp | `mesh` | `is_container` | Kết quả |
|---|---|---|---|
| `GroupLayer` không có con | `None` | `True` | một `<g>` **rỗng** được xuất ra (khớp Moho) |
| `PatchLayer` chưa giải quyết được | `None` | `False` | **không xuất ra gì cả**, kể cả `<g>` |

---

## 3. Duyệt cây layer: thứ tự quyết định

`Exporter.export_document` chứa một hàm `emit()` lồng nhau đệ quy trên cây.
Thứ tự các phép kiểm tra của nó là hành vi, không phải phong cách — nhiều
quyết định phụ thuộc vào việc xảy ra đúng tại vị trí của chúng.

```
emit(layers, world, depth, container, ancestors):

  (A) MASK FIRST, once per container
      sources = _mask_sources(container, ancestors, frame)
      if sources: emit <mask id=...>, remember clip="mask=url(#...)"
      |
      NOTE: this runs while _active_actions is EMPTY. See § 9.3.

  (B) SwitchLayer: resolve the one active child, once
      if container is a SWITCH: active_child = container.switch_active_child(frame)

  (C) for each layer in layers:          <- file order == draw order
        |
        +-- skip if not layer.visible          and not --include-hidden
        +-- skip if layer.edit_only            and not --include-hidden
        +-- skip if active_child is set and layer is not active_child
        |
        +-- world_here = world x layer.local_matrix(frame)
        |                (accumulated for STROKE WIDTH only - see § 4.3)
        |
        +-- member_clip = "" if layer.masking in (1, 2) else clip
        |                 (mask sources and exempt layers draw unclipped)
        |
        +-- if layer.mesh is not None:      ---> DRAW  (§ 3.1)
        |
        +-- elif layer.is_container:        ---> RECURSE
        |        emit(layer.children, world_here, depth+1, layer, ancestors+(layer,))
        |
        +-- else:                          ---> nothing at all
```

Ba điều đáng chú ý về thứ tự này:

- **Mask được dựng trước khi bất kỳ layer con nào được xét**, và nó được dựng
  một lần cho cả container, không phải một lần cho mỗi con. `clip` sau đó được
  áp dụng có chọn lọc cho từng con qua `member_clip`.
- **Một layer hoặc là mesh hoặc là container, không bao giờ cả hai.** Phép
  `if / elif` nghĩa là một layer giả định mang cả hai sẽ render mesh của nó và
  không bao giờ đệ quy. Không có layer nào như thế trong bất kỳ mẫu nào.
- **`visible` và `edit_only` được kiểm tra trước bất cứ thứ gì tốn kém.** Cả
  hai đều bị `--include-hidden` ghi đè cùng nhau.

### 3.1 Trình tự cho từng mesh layer

Khi `emit()` quyết định vẽ, trình tự chính xác này chạy — và hai phép gán cho
`self._active_actions` bao quanh nó:

```
self._active_actions = _active_actions_along(ancestors, frame)   # set
self._layer_scale    = world_here.uniform_scale() or 1.0
chain                = build_deform_chain(ancestors, layer, frame, self)
to_px                = _deformed_pixel_mapper(chain, frame, layer)
body, pts            = _render_mesh(layer.mesh, to_px, frame, indent)
self._active_actions = []                                        # clear
```

`export_layer` làm điều tương tự cho một layer đơn lẻ, với hai khác biệt:
`--local` thay toàn bộ chuỗi biến dạng bằng `_plain_pixel_mapper(IDENTITY)`,
và mask được tính *sau khi* `_active_actions` bị xóa (đó là nơi điểm lạ trong
[§ 9.3](#93-điểm-lạ-của-ngữ-cảnh-smart-bone-rỗng) đến từ).

### 3.2 `--flat` (`nested_groups=False`)

`--flat` triệt tiêu vỏ bọc `<g>` cho từng layer — nhưng **chỉ khi không có mask
nào để gắn vào**. Điều kiện là `if nested_groups or member_clip`. Một layer bị
mask luôn giữ `<g>` của nó, vì đó là thứ mang thuộc tính `mask=`.

---

## 4. Transform và không gian tọa độ

Đây là nơi chứa hầu hết sự tinh vi. Có **hai bước duyệt độc lập** của cùng một
chuỗi tổ tiên, tính ra hai thứ khác nhau, và chúng cố ý không khớp nhau.

### 4.1 Ma trận cục bộ riêng của một layer

`Layer.local_matrix(frame, exporter)` ánh xạ một điểm từ không gian riêng của
layer vào không gian của cha nó. Độ xoay và tỷ lệ xoay quanh `origin`, không
phải `(0,0)`:

```
p' = origin + translation + R(rotation_z) * S(scale_x, scale_y) * (p - origin)
```

`flip_h` / `flip_v` làm âm `scale_x` / `scale_y`. Chú ý tỷ lệ layer thật sự là
**theo từng trục**, trong khi `anim_scale` của một bone là một vô hướng đơn —
xem [§ 4.4](#44-ma-trận-world-của-bone).

### 4.2 Chuỗi biến dạng (hình học)

`build_deform_chain(ancestors, target, frame, exporter)` trả về một danh sách
có thứ tự các bước theo **thứ tự áp dụng**: áp `steps[0]` lên điểm mesh thô,
rồi `steps[1]`, cứ thế. Có hai loại bước:

- `MatrixStep(matrix)` — áp một phép biến đổi affine phẳng.
- `SkinStep(bone_layer, bound_bone_index)` — biến dạng bởi skeleton của bone
  layer đó.

Chuỗi được dựng bằng cách duyệt chuỗi tổ tiên **theo chiều ngược** (trong cùng
trước), gom các ma trận phẳng vào `pending` và xả chúng mỗi khi băng qua một
`BoneLayer` biến dạng:

```
raw mesh point (target's own local space)
      |
      | MatrixStep: every local_matrix between the mesh and the bone layer,
      |             composed together
      v
  BoneLayer's OWN coordinate space          <-- the skeleton's rest/pose
      |                                         matrices live in THIS space
      | SkinStep(bone_layer, bound_bone_index)
      |     bound >= 0 -> rigid:    skinner.bones[bound].rest_to_pose.apply(p)
      |     bound == -1 -> flexible: skinner.deform(p, subset, weight_fn)
      v
  still the BoneLayer's own space (now posed)
      |
      | MatrixStep: the bone layer's own local_matrix, plus everything
      |             above it (repeat for each outer BoneLayer crossed)
      v
  document space
      |
      | Exporter._to_pixel
      v
  pixel space
```

Điểm mấu chốt — và là lý do một cách tiếp cận ngây thơ "gộp mọi ma trận" cho
kết quả sai — là **skinning xảy ra trong không gian riêng của bone layer**: sau
các transform cục bộ của mọi thứ giữa mesh và bone layer, nhưng *trước*
transform riêng của bone layer. Đó là không gian mà các ma trận của skeleton
được biểu diễn trong đó.

`bound` được mang *lên* trong bước duyệt ngược: khi `build_deform_chain` đi ra
ngoài, bất kỳ layer nào có `parent_bone >= 0` đặt `bound`, thứ sau đó được
`SkinStep` kế tiếp tiêu thụ và đặt lại thành `-1`. Nên bind cứng là một thuộc
tính của chuỗi layer bên dưới một bone layer, không phải của chính bone layer.

`Exporter._to_pixel` khép vòng (xem `moho-project-file-format.md` § 4):

```
pixel_x = moho_x * (height/2) + width/2
pixel_y = height/2 - moho_y * (height/2)        # y flipped
```

### 4.3 Chuỗi tỷ lệ (stroke width), và vì sao nó khác

Stroke width dùng một bước duyệt **hoàn toàn tách biệt**:
`_full_chain_matrix(ancestors, layer, frame)` trong `export_layer`, hoặc
`world_here` được tích lũy trong `export_document`. Cả hai gộp mọi
`local_matrix` trong chuỗi **kể cả của chính layer**, và cả hai **loại trừ
hoàn toàn biến dạng bone**.

```
_stroke_width_px(line_width, point_width) =
      line_width
    * point_width
    * settings.stroke_width_scale        # --stroke-mul, default 2.0
    * document.height / 2.0
    * self._layer_scale                  # uniform_scale() of the matrix chain
```

Ở mặc định `--stroke-mul 2.0`, `stroke_width_scale * height/2` thu gọn thành
`height`, là công thức rút gọn được trích dẫn trong `moho-project-file-format.md` § 7.6.

Loại trừ biến dạng bone là **cố ý và đã được đo**: bao gồm nó làm lạm phát tỷ
lệ biểu kiến ~11% trên một bài kiểm tra vòng đi. Xem phần STROKE WIDTH trong
docstring của module.

| | Hình học | Stroke width |
|---|---|---|
| Được dựng bởi | `build_deform_chain` | `_full_chain_matrix` / `world_here` |
| Bao gồm biến dạng bone | **có** | **không** |
| Bao gồm transform riêng của layer | có | có |
| Đầu ra | một danh sách các bước, áp theo từng điểm | một vô hướng, `uniform_scale()` |

### 4.4 Ma trận world của bone

`Skeleton.world_matrices(frame, exporter)` trả về một ma trận cho mỗi bone.
Cha được giải quyết **trước** con bất kể thứ tự danh sách — danh sách bones
không được đảm bảo sắp xếp topo, nên chuỗi cha của mỗi bone được duyệt theo
nhu cầu kèm ghi nhớ.

Ma trận cục bộ của mỗi bone là:

```
local = Mat2D(cos*scale, sin*scale, -sin, cos, pos.x, pos.y)
                ^^^^^^^  ^^^^^^^^   ^^^^  ^^^
                first column scaled   second column NOT scaled
```

Sự bất đối xứng đó **được giữ cố ý, và được gắn cờ thay vì sửa**: nó vượt qua
mọi bài kiểm tra hồi quy sẵn có, nhưng không mẫu nào luyện tập một bone có
`anim_scale` xa `1.0` theo cách phân biệt được tỷ lệ bất đối xứng với tỷ lệ
đều. Đừng "sửa" nó nếu không có bằng chứng tham chiếu mới. Xem KNOWN GAPS
trong docstring của module.

### 4.5 Skinning: cứng so với mềm

`Skinner.build(skeleton, frame, exporter)` tính sẵn, cho mỗi bone, các đầu mút
segment ở pose nghỉ và `rest_to_pose = pose[i] * rest[i]⁻¹`, trong đó rest
luôn được đánh giá tại **frame 0.0**.

`Skinner.deform(p, subset, weight_fn)` sau đó blend:

```
for each bone i in (subset if subset else all bones):
    if bone.strength <= 0:  skip        <- Moho's "this bone does not deform
                                           this mesh" gate, checked FIRST
    w = weight_fn(distance_to_segment(p, rest_p0, rest_p1), bone.strength)
    if w <= 0: skip
    acc   += rest_to_pose.apply(p) * w
    total += w
result = acc / total   (or p unchanged if total == 0)
```

Falloff mặc định là `inv_d2` (`1/d²`), được chọn bởi
`RenderSettings.bone_weight_falloff`. Ba phương án thay thế (`linear`,
`cut_d2`, `hermite`) được giữ trong `BONE_WEIGHT_FALLOFFS` vì chúng đã được
thử trong lúc phát triển và **không thể phân biệt với `inv_d2` bằng bất kỳ
tham chiếu sẵn có nào** — không phải vì chúng được biết là đúng ngang nhau.

---

## 5. Đánh giá channel và ghi đè Smart Bone

### 5.1 `Channel.of` và bộ cache định danh

Mọi trường hoạt ảnh đi qua `Channel.of(raw)`, thứ chấp nhận hoặc một đối tượng
channel thật hoặc một vô hướng trần (được coi như một keyframe đơn). Kết quả
được cache **theo `id(raw)`**.

Điều đó an toàn chứ không phải chỉ may mắn, và nó phụ thuộc vào thiết kế
accessor mỏng: vì mô hình tài liệu không bao giờ sao chép các dict channel,
cùng một channel logic luôn là cùng một đối tượng Python trong suốt đời của
một `Document`. Hai channel khác nhau không thể đụng nhau, và `Channel` đã
cache là bất biến. Nếu một thay đổi trong tương lai bắt đầu sao chép dict thô,
bộ cache này trở nên không an toàn.

### 5.2 Hai điểm vào đánh giá

```
Exporter.eval(raw, frame)      -> Channel.of(raw).eval(frame, self._active_actions)
Exporter.eval_raw(raw, frame)  -> Channel.of(raw).eval_raw(frame)
```

`eval_raw` là nội suy tuyến tính từng mảnh thường, kẹp ở cả hai đầu:

- số → nội suy tuyến tính
- dict `{x,y}` / `{x,y,z}` / `{r,g,b,a}` → nội suy tuyến tính theo từng khóa
- **chuỗi và bool → bám vào keyframe bên trái** (không nội suy)

`interp` không bao giờ được hỏi. Nên kết quả chính xác *tại* keyframe và xấp xỉ
giữa chúng — xem `moho-project-file-format.md` § 5.3.

`eval` trước tiên kiểm tra các dial Smart Bone đang hoạt động:

```
for active in active_actions:            # priority order, root-first
    pose = channel.action_pose(active.name)
    if pose is not None:
        return pose.eval_raw(active.frame)     # <- action frame, NOT document frame
return channel.eval_raw(frame)
```

**Khớp đầu tiên thắng**, đó là lý do `active_actions` phải đã sẵn theo thứ tự
ưu tiên.

### 5.3 Một dial trở nên hoạt động thế nào

`_active_actions_along(ancestors, frame)` gọi `_active_smart_bones` cho mọi
`BoneLayer` tổ tiên, **gốc trước** — nên dial của một bone layer ngoài có thứ
hạng cao hơn dial của một bone layer trong nếu cả hai tình cờ ảnh hưởng cùng
một channel.

Với một bone layer, `_active_smart_bones(bone_layer, frame)` làm:

```
names = bone_layer.action_names            # the layer's own actions[] registry
for bone in bone_layer.skeleton.bones:
    if bone.name not in names:  continue   # <- THIS is what makes it a "dial"
    current = Channel.of(bone.anim_angle).eval_raw(frame)   # NOT eval()
    for action in that channel's own actions:
        if action.name not in names: continue
        lo, hi = min(action.pose.val), max(action.pose.val)
        if hi - lo < 1e-9: continue                  # degenerate, unusable
        inside   = lo <= current <= hi
        distance = 0 if inside else min(|current-lo|, |current-hi|)
        key      = (distance, -span)                 # closest first, then widest
    best -> ActiveAction(name, action.pose.frame_for_value(current))
```

Ba điểm dễ làm sai:

1. **Một bone là dial chỉ khi tên của chính nó xuất hiện trong registry
   `actions` của layer.** Tên action khớp với không bone nào là các action
   dòng thời gian thường và không bao giờ được kích hoạt — xem
   `moho-project-file-format.md` § 11.3.
2. **`eval_raw` là bắt buộc ở đây.** Đây là nơi *duy nhất* trong codebase cần
   nó: giải quyết góc hiện tại của chính một dial không được đệ quy vào cỗ máy
   ghi đè mà dial là một phần. Dùng `eval` sẽ là đệ quy vô hạn, hoặc tệ nhất là
   sai.
3. **Đường cong pose được đảo ngược, không phải được lấy mẫu.**
   `frame_for_value(current)` hỏi "pose này có góc dial tại frame nào bằng góc
   dial *thực sự đang* ở bây giờ?" — mảng `val` của channel pose ghi góc của
   chính dial tại mỗi keyframe pose. Đây là lý do Moho lưu hai action cho mỗi
   dial (cái thứ hai hậu tố `" 2"`): một đường cong phải gần đơn điệu mới đảo
   ngược được.

### 5.4 Khóa cache của skinner

`Exporter._skin_data` cache theo `(bone_layer, frame, tuple(self._active_actions))`.
Ngữ cảnh Smart Bone **phải** là một phần của khóa, vì một dial đang hoạt động
thay đổi chính các giá trị `anim_angle` của bones và do đó thay đổi toàn bộ
pose. Hai mesh layer dưới cùng một bone layer ở cùng một frame chỉ dùng chung
một `Skinner` nếu ngữ cảnh dial của chúng giống hệt nhau.

---

## 6. Từ mesh đến dữ liệu path

### 6.1 Đánh giá hình học curve

`Exporter._curve_geometries(mesh, frame)` chạy một lần cho mỗi mesh layer,
trước khi bất kỳ shape nào được vẽ:

```
positions = [eval(p.position, frame) for p in mesh.points]     # once for the whole mesh
for each curve:
    widths = [eval(mesh.points[cp.point_index].width, frame) for cp in curve.points]
    CurveGeometry.build(curve, positions, bezier, frame, exporter, widths)
```

`CurveGeometry.build` tạo ra một `SegmentGeometry` cho mỗi segment, mỗi cái giữ
một Bezier bậc ba tường minh (`p0, c1, c2, p1`) cộng `on`:

| Trường `SegmentGeometry` | Đến từ |
|---|---|
| `p0` | `positions[curve.points[i].point_index]` |
| `p1` | `positions[curve.points[(i+1) % n].point_index]` — quấn lại cho một curve kín |
| `c1` | `BezierReconstructor.handle(curve, positions, i, False, ...)` |
| `c2` | `BezierReconstructor.handle(curve, positions, j, True, ...)` |
| `on` | `curve.points[i].segments_on` — **segment rời khỏi điểm `i`** |

**Độ dài** tay cầm là `distance_to_neighbour * smoothness * weight` (đã xác
nhận chính xác so với 209 tay cầm tham chiếu). **Hướng** tay cầm *không* phải
`normalize(next - prev)`; nó là một blend có trọng số theo độ dài dây cung của
hai vector dây cung lân cận. Xem phần BEZIER CURVES trong docstring của module.

Chú ý `CurveGeometry.point_widths` song song với danh sách **điểm của chính
curve**, không phải của mesh. Hãy lập chỉ số nó cho đúng.

### 6.2 `PathTracer`: dựng lại thứ tự duyệt

`build_path_d` không thể đơn giản nối `edges` theo thứ tự danh sách.
`PathTracer.trace`:

1. Dựng một bản đồ kề vô hướng khóa theo tọa độ đầu mút **đã làm tròn**
   (`Vec2.rounded_key()`), để các segment dùng chung một điểm được nhận ra dù
   có nhiễu float.
2. Gieo các bước duyệt **ưu tiên một đầu mút chạm đúng một segment** (một đầu
   hở thật sự) hơn là một điểm nối, để các điểm nối bị hấp thụ giữa chừng thay
   vì trở thành ranh giới subpath tùy ý.
3. Duyệt từng dải liên thông, đảo ngược các điểm điều khiển của một segment
   khi nó được vào từ đầu `p1` của nó.

`build_path_d` sau đó sinh ra các lệnh `M`/`C`, bắt đầu một subpath mới mỗi khi
segment kế tiếp không nối tiếp từ đầu mút trước đó.

### 6.3 Hai cờ làm thay đổi đầu ra

```
build_path_d(geometries, edges, to_px, visible_only=False, close=True)
```

| Cờ | Path tô | Path viền |
|---|---|---|
| `visible_only` | `False` — một segment ẩn vẫn chặn phạm vi của phần tô | `True` — bỏ qua các segment `segments_on == False` và bẻ gãy subpath |
| `close` | `True` — thêm `Z` khi subpath trở về điểm bắt đầu | **`False` — không bao giờ đóng một nét viền** |

Không bao giờ đóng một path nét viền không phải là sơ suất: chính exporter của
Moho cũng không đóng chúng. Xem phần FILL RULE, DRAW ORDER, AND WHY STROKE
PATHS ARE NEVER CLOSED trong docstring của module.

---

## 7. Từ shape đến phần tử SVG

`ShapeGroupRenderer` vẽ mọi shape của một mesh, theo thứ tự `mesh.shapes`
(đó *chính là* z-order, sau ra trước).

### 7.1 Vì sao shapes phải được lưu đệm

Đường viền của một thành viên union phải được cắt theo các thành viên *khác*
của nhóm boolean của nó — và chúng có thể chưa được render. Nên:

- **Phần tô được xuất ra ngay lập tức**, vào `self.body`.
- **Đường viền được lưu đệm** vào `self._group` dưới dạng các bản ghi
  `_GroupMember`, và chỉ trở thành phần tử `<path>` trong `_flush()`.

`_flush()` được gọi từ đúng hai nơi: lúc bắt đầu `_render_shape` khi một shape
`combo_mode == 0` bắt đầu một nhóm mới, và một lần ở cuối `render()` cho nhóm
cuối cùng.

```
render():
  for shape in mesh.shapes:
      _render_shape(shape)      --> fill emitted now; outline queued
  _flush()                      --> last group's outlines emitted
  return self.defs + self.body
         ^^^^^^^^^^   ^^^^^^^^^
         ALL defs come before ALL body elements
```

### 7.2 Bên trong `_render_shape`

```
skip if not shape.edges
resolve colours/width:  eval(style.line_width), eval(style.fill_color),
                        eval(style.line_color), style.line_cap_name()
fill_path = build_path_d(..., close=True)     # skip the shape entirely if empty

paint = fill_hex
if shape.has_fill and style.fill_style is a dict:
    if type == "SS_Gradient2": build a gradient def, paint = url(#grad_N)
    else:                      warn to stderr, keep the flat colour

widths      = _point_widths(shape.edges)      # distinct mesh points of this shape
tapered     = (max(widths) - min(widths) > 1e-6)
point_width = widths[0] if (widths and not tapered) else 1.0

combo_mode = shape.combo_mode
if combo_mode not in (0, 1, 3):  warn, treat as 0     # <- this is where 2 lands
if combo_mode == 0 or group is empty:  _flush()

if combo_mode == 3:  clip = union of the group's solid members SO FAR

if shape.has_fill:  emit <path ..._fill> now
if shape.has_outline:  pick exactly ONE outline strategy (below), queue it
```

Chú ý `combo_mode == 3` được cắt **hai lần**: một lần ở đây so với các thành
viên đặc của nhóm đã biết cho tới nay, và một lần nữa trong `_flush()` so với
tập đặc cuối cùng của nhóm.

### 7.3 Ba chiến lược nét viền

Đúng một chiến lược áp dụng cho mỗi shape, được chọn theo thứ tự này:

```
if brush asset resolved (style.brush_name AND style.brush_tint AND file found):
        BrushStampOutliner.build(...)  -> brush_dabs
        diameter comes from _stroke_width_px(line_width, 1.0)
        NOT ...(line_width, point_width) - each dab scales itself by the
        point width interpolated at that dab, so baking it in twice is wrong
elif tapered:
        TaperedStrokeOutliner.build(...)  -> taper_path  (a filled outline)
else:
        build_path_d(..., visible_only=True, close=False)  -> stroke_path
```

Một nét cọ thắng việc làm thon — một shape có cọ với bề rộng thay đổi vẫn được
xử lý bằng cọ, với độ thon gấp vào đường kính của từng dab.

### 7.4 `_flush()` xuất ra những gì

```
base  = self._group[0]                                    # the group's styling source
solid = [m.fill_path for m in group if m.combo_mode in (0, 1)]

for member in group:
    skip if it has no outline of any kind
    style_source = base if member.combo_mode in (0,1) else member
                   ^^^^ a union member is stroked with the BASE's style,
                        not its own - this is Moho's behaviour
    clip:
      combo_mode in (0,1) and len(solid) > 1 -> _mask_subtraction(others, own, ...)
      combo_mode == 3                        -> _mask_union(solid, ...)

    then emit ONE of:
      brush_dabs -> <g id="NAME_line" clip>  ... dabs ...  </g>
      taper_path -> <path id="NAME_line" fill=LINE fill-rule="evenodd" stroke="none">
      stroke_path-> <path id="NAME_line" fill="none" stroke=LINE
                          stroke-width stroke-linecap stroke-linejoin="round">
```

`_mask_subtraction` đáng được hiểu, vì nó mã hóa hai sửa lỗi riêng biệt:

1. Nó đục lỗ bằng **một path even-odd duy nhất** (bbox có đệm trừ đi mọi thành
   viên khác), không phải một rect trắng đằng sau các hình đen. Cách sau render
   sai trong `cairosvg`, thứ coi nội dung mask là alpha thay vì luminance.
2. Rồi nó sơn lại **một dải rộng đúng một stroke-width lên trên** dọc theo mọi
   path bị trừ. Không có nó, hai đường viền cắt nhau mỗi cái dừng đúng trên mép
   của cái kia, thiếu một stroke-width để gặp nhau, để lại một khấc thấy được.

Có một giới hạn đã biết ở đây, được gắn cờ thay vì vá: shape "của mình" được
truyền để đo kích thước mask là `member.stroke_path`, thứ là `""` với một thành
viên làm thon hoặc đóng dấu cọ. Thành viên như thế chỉ dựa vào phạm vi của các
thành viên *khác*. Không mẫu nào luyện tập nó như một thành viên union không
phải base.

**Một giới hạn thứ hai, giờ đã được sửa: clip `_mask_union` của `combo_mode ==
3` là một xấp xỉ *masking SVG* của phép giao, không phải một phép giao hình học
path thật — thứ từng để lại một lỗ thật trên đường viền riêng của thành viên
mà Moho không hiển thị.** Đã xác nhận trên `Eye_Upper`/`S3` của `Bandit` (một
shape `combo_mode == 3`): một trong các segment curve của nó có
`segments_on == false`, nhưng các đầu mút của chính segment đó không trùng với
bất kỳ segment nào của đường biên shape base — khác với trường hợp
`combo_mode == 1` ở trên, nơi một segment ẩn hợp pháp là một cạnh dùng chung mà
thành viên *khác* đã vẽ, segment này là hình học độc nhất không có gì thay thế
nó. `build_path_d` (§ 6.3) với `visible_only=True` đơn giản bỏ qua nó, để lại
hai subpath hở với nắp tròn thay vì một vòng kín — thấy được như một khấc nhỏ.
Moho thật nhiều khả năng tính một cạnh ranh giới mới thật sự nơi hai curve cắt
nhau, và đánh dấu segment gốc `segments_on == false` vì một cạnh *được tính*
đã thay thế nó.

Thay vì dựng lại cạnh đó (phép giao Bezier–Bezier thật — tìm điểm cắt và xây
một segment mới tại đó, một lớp thuật toán khác với cách clip-stroke-sẵn-có
của `_mask_union`), nhánh nét viền thường của `_render_shape` (§ 7.2) giờ
truyền `visible_only=(combo_mode != 3)` cho `build_path_d` thay vì luôn `True`.
Với một thành viên `combo_mode == 3`, điều này vẽ **toàn bộ** đường viền kín
gốc — kể cả segment segments_on==false — và để clip `_mask_union` *sẵn có*
(không đổi) cắt nó xuống trong phần tô của shape base, đúng như nó đã làm với
các segment thấy được. Vì chính clip của SVG tính điểm cắt hình học thật khi
mask được raster hóa, kết quả ra đúng mà công cụ này không bao giờ tự tính một
phép giao Bezier. Đã xác nhận: `S3_line` của `Eye_Upper` đổi từ hai subpath
(bị cắt bởi một `M`) thành một path liên tục, khép lỗ thấy được, và — kiểm
chéo trên cả năm tài liệu tham chiếu — `Eye_Upper`/`S3` là shape **duy nhất**
vừa `combo_mode == 3` vừa có một segment `segments_on == false`, nên không gì
khác có thể bị hồi quy. Xem phần BOOLEAN SHAPE COMBINATIONS trong docstring
của module và KNOWN GAPS cho câu hỏi mở còn lại duy nhất (liệu một thành viên
intersect có thể hợp pháp muốn một lỗ do chính nghệ sĩ vẽ hay không, thứ sửa
lỗi này giờ sẽ khôi phục thay vì che giấu).

### 7.5 Ba đường render cọ

Được chọn trong `_flush()`, theo shape:

| Điều kiện | Đường | Phần tử cho mỗi dab |
|---|---|---|
| `--brush-raster` và có Pillow | `_raster_brush_shape` gộp toàn bộ nét vẽ thành **một** `<image>` | không — một ảnh cho mỗi shape |
| có Pillow (mặc định) | `_brush_tinted_ref` bake màu một lần cho mỗi `(brush, frame, colour, alpha)` | `<use>` của một `<image>` đã nhuộm sẵn |
| **không** có Pillow | `_brush_mask_refs` | `<mask>` + `<filter>` cho mỗi dab — đường fallback chậm |

Đường fallback chậm để *xem*, không chỉ chậm để ghi: `<mask>` và `<filter>` mỗi
cái ép một bộ đệm ngoài màn hình cho mỗi phần tử. Xem `docs/moho-exporting-svg.md`
§ 7 cho các con số đã đo.

### 7.6 `PatchLayer` bỏ nét viền của chính nó, không chỉ transform

`ShapeGroupRenderer` nhận một cờ `suppress_outline`, được cả hai nơi gọi đặt
(`Exporter.export_layer` và `emit()` của `export_document`) mỗi khi layer đang
được render có `layer.kind is LayerKind.PATCH`:

```
outline_enabled = shape.has_outline and not self.suppress_outline
```

`outline_enabled` thay thế `shape.has_outline` ở cả hai nơi quyết định có xây
một nét viền hay không: tra cứu brush asset và nhánh
`stroke_path` / `taper_path` / `brush_dabs`. Đường **tô** không bị đụng tới —
`shape.has_fill` vẫn điều khiển nó trực tiếp.

Điều này tồn tại vì một patch đã giải quyết dùng chung nguyên văn các đối
tượng `Shape` của target ([§ 2.3](#23-hai-phép-viết-lại-lúc-tải)):
`shape.has_outline` trên các shape của một patch thật ra là `has_outline` của
*target*, và target có một nét viền thật của riêng nó mà vẫn phải render ở bất
kỳ đâu bản thân target vẽ trong cây. Biến đổi `Shape.has_outline` sẽ làm câm
lặng cả cái đó, nên việc triệt tiêu phải là một cờ ở lúc render, được kiểm một
lần cho mỗi lượt render, không phải một thuộc tính của shape dùng chung.

Vì sao lại triệt tiêu nét viền: đã xác nhận trực tiếp trong ứng dụng Moho
(không chỉ bằng cách so sánh đầu ra SVG của chính công cụ này với chính nó)
trên hai điểm được chọn cụ thể để tách điều này khỏi hành vi masking được ghi
lại trong [§ 9](#9-masking-hai-trường-một-cấu-trúc-svg):

| Layer | `masking` | Có là `PatchLayer` | Target có nét viền thật | Nét viền thấy được trong Moho |
|---|---|---|---|---|
| `ayasi-Patch` (SketchBone) | `2` (mask source) | có | có | **không** |
| `Left Bicep-Patch` (ReparentBone) | `0` (không phải mask source) | có | có | **không** |

`masking` là trường duy nhất khác nhau giữa hai cái, và kết quả không đổi — nên
việc triệt tiêu khóa theo `layer.kind is LayerKind.PATCH`, không phải theo
`masking`. Điều này cũng nghĩa là nó *không* mâu thuẫn với khẳng định đã xác
nhận của [§ 9](#9-masking-hai-trường-một-cấu-trúc-svg) rằng "một layer
`masking == 2` vẫn được vẽ bình thường" — quy tắc đó nói về tính thấy được, chứ
không về phần nào của kiểu riêng của một mesh layer thường được áp dụng, và nó
chưa bao giờ được kiểm thử với một `PatchLayer` cụ thể.

---

## 8. Giải quyết style và ánh xạ thuộc tính SVG

### 8.1 Việc giải quyết xảy ra khi nào

`ResolvedStyle.resolve(shape_raw, styles)` được gọi **một lần cho mỗi shape ở
lúc tải**, từ `Shape._build` — không bao giờ theo frame. Kế thừa không bao giờ
phụ thuộc vào một frame, nên không có gì để làm lại.

Thứ nó tạo ra *vẫn là* các channel, không phải giá trị: `fill_color`,
`line_color`, và `line_width` giữ nguyên thô để chúng có thể được đánh giá
theo từng frame với ngữ cảnh Smart Bone đúng. Chỉ `line_caps` được lưu như một
`int` thường (Moho không bao giờ hoạt ảnh nó).

### 8.2 Quy tắc gộp, chính xác

```
own = shape_raw["style"]
out = dict(own)                                  # <- the shape's own values are the BASE
for key in (inherited_style_uuid, inherited_style_name,
            inherited_style2_uuid, inherited_style2_name):
    ref   = shape_raw.get(key) or own.get(key)   # BOTH locations are checked
    named = styles.get(ref)                      # by uuid OR name
    if not named: continue
    for (flag, field) in [(define_fill_color, fill_color),
                          (define_line_col,   line_color),
                          (define_line_width, line_width)]:
        if named[flag] and not own[flag]:  out[field] = named[field]
    if named.fill_style is a dict and not own.define_fill_color:
        out.fill_style = named.fill_style        # gradients live ONLY on named styles
    if not own.define_line_width and "line_caps" in named:
        out.line_caps = named.line_caps
    if named.define_line_width and not own.define_line_width and named.brush_name:
        copy brush_name, brush_jitter, brush_spacing, brush_align, brush_tint
```

Hai hệ quả hay làm người ta bất ngờ:

- **Một cờ `define_X` false trên shape không làm trống giá trị riêng của
  shape.** Nó chỉ làm shape trở nên *có thể bị ghi đè*. Đây là lý do thế hệ tài
  liệu mới hơn hoạt động được: mọi shape của nó có mọi cờ false và không có
  style kế thừa, nên các giá trị riêng của nó được dùng nguyên văn.
- **Style 2 được áp dụng sau style 1**, nên style 2 thắng nơi cả hai định nghĩa
  cùng một thuộc tính. Đó là cơ chế đằng sau việc đặt một "line style" chỉ-có-
  viền lên trên một fill style nền.
- **`fill_style`, `line_caps`, và các trường cọ cưỡi trên cùng ba cờ.** Đặc
  biệt một cây cọ được gác cổng bởi `define_line_width`, vì một cọ chỉ bao giờ
  tạo kiểu cho đường nét.

### 8.3 Trường → thuộc tính SVG

| Trường đã giải quyết | Xuất ra thành | Ghi chú |
|---|---|---|
| `fill_color` | `fill="#RRGGBB"` + `fill-opacity` | được bỏ qua khi alpha ≥ 1 |
| `fill_style` (`SS_Gradient2`) | `fill="url(#grad_N)"` + một def gradient | `gradient_type` 1 → `<radialGradient>`, bất kỳ cái gì khác → `<linearGradient>`. Xem ghi chú bên dưới. |
| `line_color` | `stroke="#RRGGBB"` + `stroke-opacity` — **hoặc** `fill=` trên một nét viền làm thon/cọ | một nét viền làm thon là một path *được tô*, nên màu đường nét trở thành một màu tô |
| `line_width` × điểm `width` | `stroke-width` | qua `_stroke_width_px`; xem [§ 4.3](#43-chuỗi-tỷ-lệ-stroke-width-và-vì-sao-nó-khác) |
| `line_caps` | `stroke-linecap` | `LINE_CAP_NAMES = {0: butt, 1: round, 2: square}`, mặc định `round` |
| — | `stroke-linejoin="round"` | viết cứng, không lấy từ tài liệu |
| phần tô | `fill-rule="evenodd"` | trên phần tô shape và nét viền làm thon |
| nội dung mask | `fill-rule="nonzero"` | **cố ý khác** với phần tô |
| `brush_*` | `<image>` / `<use>` / `<mask>`+`<filter>` | xem [§ 7.5](#75-ba-đường-render-cọ) |
| `shape.effect_scale` / `effect_rotation` | chỉ dùng cho vị trí gradient | không phải một transform hình học |

Việc tách `evenodd` (phần tô) với `nonzero` (mask) là cố ý. Một mask dựng bằng
`evenodd` sẽ tự triệt tiêu bất kỳ nơi nào hai mask source chồng nhau.

Ba chi tiết về gradient trong `_build_gradient` dễ bỏ sót:

- **Ít hơn hai stop → không có gradient chút nào.** Nó trả về `(None, None)`
  và shape giữ `fill_color` phẳng của nó, một cách thầm lặng.
- **Vị trí là phần trăm, tâm tại `50% / 50%`**, tức là tương đối với bounding
  box riêng của mỗi path (đơn vị `objectBoundingBox` mặc định của SVG). Đây là
  lý do vị trí chỉ xấp xỉ thay vì khớp pixel với vị trí được tham số hóa khác
  của riêng Moho.
- **`effect_rotation` chỉ ảnh hưởng trường hợp tuyến tính.** Nhánh radial dùng
  `effect_scale` cho `r` và bỏ qua độ xoay hoàn toàn — một gradient radial bị
  xoay là một no-op. Một độ lệch tâm cấp shape được công thức hỗ trợ nhưng
  không gì cung cấp nó, nên nó ở lại `(0, 0)`.

---

## 9. Masking: hai trường, một cấu trúc SVG

### 9.1 Quy tắc

Hai trường tách biệt phối hợp với nhau (ngữ nghĩa đầy đủ trong
`moho-project-file-format.md` § 10):

- `group_mask` trên **container** — khác không nghĩa là "container này mask các
  con của nó". `Exporter._mask_sources` trả về sớm khi nó falsy, trừ khi
  `--mask-container NAME` ép nó.
- `masking` trên mỗi **con** — `2` = mask source (vẫn được vẽ bình thường),
  `1` = miễn trừ, bất kỳ cái gì khác = bị cắt.

### 9.2 Thu thập hình bóng, đệ quy

`_mask_source_shapes(layer, ancestors, frame)` gom hình học mask cho một layer
`masking == 2`, dưới dạng các cặp `(fill_path, own_stroke_width_px)` — phần tử
thứ hai là `0.0` trừ khi shape có một nét viền thường (không làm thon, không
cọ), trong trường hợp đó nó là stroke width đã giải quyết của chính nét viền
đó, được tính cùng cách với `stroke_width_px` của `_render_shape`:

```
paths = []
if layer.mesh is not None:
    build its own deform chain
    for each shape: append (fill_path, own_stroke_width_px_or_0.0)
for child in layer.children:
    if child.masking == 2:
        paths += _mask_source_shapes(child, ancestors + (layer,), frame)   # recurse
return paths
```

`_mask_element` (§ 9.5) dùng phần tử thứ hai của mỗi cặp để đục dải stroke của
riêng source ra khỏi mask, để nó không bao giờ bị vẽ đè bởi bất cứ thứ gì mask
cắt.

Phép đệ quy không phải là lý thuyết. Một mask source **không phải lúc nào cũng
là một mesh layer**: một `GroupLayer` có thể là `masking == 2` thuần túy như
một *container* mask, trong trường hợp đó hình bóng của nó là bất cứ thứ gì các
con `masking == 2` của chính nó định nghĩa. Đã xác nhận với `BellyTexture` của
rig `Bandit`, có `mesh` riêng là `None` và con `masking == 2` duy nhất `Body`
đúng là shape mà xuất của chính Moho dùng vừa làm clip nội bộ của
`BellyTexture` vừa làm đóng góp của nó cho việc mask anh em của nó.

Masking áp dụng **đều ở mọi độ sâu, kể cả gốc tài liệu**. Một phiên bản cũ từng
đối xử đặc biệt với masking ở cấp cao nhất; hóa ra đó là sửa sai cho một lỗi
không liên quan.

### 9.3 Điểm lạ của ngữ cảnh Smart Bone rỗng

`_mask_sources` luôn được đánh giá với `self._active_actions` **rỗng** — không
bao giờ với các dial đang hoạt động cho mesh đang bị cắt.

Đây không phải một quyết định thiết kế. Nó rơi ra từ *khi nào* `export_layer` /
`export_document` gọi nó so với nơi chúng đặt và xóa `_active_actions`: do cấu
tạo, nó luôn nằm giữa hai lần xóa. Nó đã được **giữ cẩn thận thay vì sửa**, vì
không có xuất tham chiếu nào để xác nhận điều gì nên xảy ra thay thế. Nếu bạn
sắp xếp lại các phép gán đó, bạn thay đổi hình học mask cho bất kỳ rig nào có
mask source bị điều khiển bởi một Smart Bone. Xem KNOWN GAPS trong docstring
của module.

### 9.4 SVG tạo ra trông thế nào

```
<svg viewBox="...">
  <defs>                          <- brush defs only (see § 10)
    <image id="brush_.."/>  ...
  </defs>
  <mask id="mask_1" maskUnits="userSpaceOnUse" x=".." y=".." width=".." height="..">
    <path d="<source silhouette>" fill="white" fill-rule="nonzero"/>
    ...                                                     one per mask source
  </mask>
  <g id="ContainerName" data-moho-type="GroupLayer">
    <g id="MaskSourceChild" data-moho-mask="2">              <- NOT clipped
      <path id="S1_fill" .../>
    </g>
    <g id="ClippedChild" data-moho-mask="0" mask="url(#mask_1)">
      <path id="S2_fill" .../>
      <path id="S2_line" .../>
    </g>
    <g id="ExemptChild" data-moho-mask="1">                  <- NOT clipped
      ...
    </g>
  </g>
</svg>
```

Các điểm đáng chú ý:

- `<mask>` được xuất ra **nội tuyến**, ngay trước các con của container — không
  phải trong `<defs>`. Chỉ các def cọ mới vào `<defs>`.
- Mọi mask có một `maskUnits="userSpaceOnUse"` tường minh cộng một bbox được
  tính bởi `parse_path_bbox(paths, settings.mask_padding)`. Không có hộp tường
  minh, vùng `objectBoundingBox` mặc định cắt chính mask.
- `data-moho-mask` và `data-moho-type` là các trợ giúp gỡ lỗi mà công cụ này
  thêm vào; chúng không mang ý nghĩa render nào.
- Một `<mask>` được dùng thay vì một `<clipPath>` nhiều con vì một `<clipPath>`
  với nhiều con không hợp chúng lại theo cách cần thiết ở đây.

### 9.5 Nét viền riêng của một mask source không bao giờ được vẽ đè lên

Nét viền đã render của chính một anh em `masking == 2` vẫn thấy đầy đủ trên bất
cứ thứ gì nó mask — đã kiểm chứng trực tiếp với ứng dụng Moho trên cặp
`Head_DarkBlue` (`masking == 0`) / `BellyTexture` (`masking == 2`) của
`Bandit.mohoproj`: nét viền của `BellyTexture` hiện không đứt đoạn trong Moho
ở mọi nơi nó chồng lên `Head_DarkBlue`. Trước khi điều này được sửa, vì
`BellyTexture` được liệt kê *trước* `Head_DarkBlue` trong `layers`, công cụ này
để `Head_DarkBlue` vẽ đè lên khoảng hai phần ba trong của nét viền
`BellyTexture` ở mọi nơi hình học chưa-mask của chúng chồng nhau — đã xác nhận
bằng cách raster hóa cả hai độc lập (`rsvg-convert`) và so sánh màu pixel dọc
theo đường tâm nét viền của `BellyTexture`: ~65% pixel nét viền được lấy mẫu
hiện màu sai.

**Sửa hiển nhiên (đổi thứ tự sơn) đã được thử trước và bị hoàn tác.** Làm cho
`emit()` sơn mọi anh em `masking == 2` sau mọi anh em `masking == 0` trong cùng
container sửa đúng cặp cụ thể này, nhưng phá vỡ một quan hệ khác, không bị đụng
tới, trên *cùng* container: hầu hết các con riêng của `Bandit` (`Arm_B`,
`Tail`, `Ears`, `Muzzle`, `Nose`, `EyeBrow`, `Arm_F`) là `masking == 1`
("miễn trừ"), và `BellyTexture` nguyên thủy đứng trước một số trong chúng (ví
dụ `Muzzle`) theo thứ tự file. Ép "mọi masking==2 sau mọi masking==0" kéo
`BellyTexture` vượt qua cả các anh em miễn trừ đó, sơn phần tô đục của nó lên
mắt/mõm/mũi của nhân vật — đã xác nhận sai trong ứng dụng Moho (`Muzzle`/`Nose`/
`EyeBrow` không bị ảnh hưởng ở đó). Cụ thể: `BellyTexture` sẽ cần sơn cả
*trước* `Muzzle` (giữ thứ tự miễn trừ không bị đụng tới) lẫn *sau*
`Head_DarkBlue 2` (quy tắc masking==2-sau-masking==0 mới) — nhưng `Muzzle` đã
đứng trước `Head_DarkBlue 2` theo thứ tự file, nên hai yêu cầu đó loại trừ lẫn
nhau. Không có một sự sắp xếp lại nào của các con trong một container thỏa cả
hai ràng buộc cho tài liệu này — một sửa theo thứ tự sơn là loại sửa hoàn toàn
sai phạm trù.

**Sửa thật thay đổi hình *học* của mask, không phải thứ tự sơn.**
`_mask_source_shapes` (§ 9.2) giờ trả về, cho mỗi shape source, không chỉ path
tô của nó mà còn stroke width riêng của nó theo pixel — được tính cùng cách
`_render_shape` tính `stroke_width_px` (§ 7), và để ở `0.0` (không loại trừ) mỗi
khi shape làm thon hoặc có cọ, vì một dải stroke-width đều sẽ không khớp hình
học thật của bất kỳ đường viền nào trong hai loại đó. `_mask_element` sau đó
sơn mỗi path như thế một lần **thứ hai**, sau phần tô trắng của nó (nên nó
thắng), như một **nét viền đen** đúng bề rộng đó — đục dải stroke của riêng
source *ra khỏi* mask:

```python
def _mask_element(self, paths, mask_id, indent):
    fills = "".join(f'<path d="{d}" fill="white" fill-rule="nonzero"/>' for d, _ in paths)
    exclusions = "".join(
        f'<path d="{d}" fill="none" stroke="black" stroke-width="{w:.3f}"/>'
        for d, w in paths if w > 0)
    ...  # fills, THEN exclusions, in that order inside the same <mask>
```

Bất cứ thứ gì mask này cắt giờ không thể bao giờ sơn vào dải bị loại trừ đó,
**bất kể nó ở z-order nào** — đây là lý do sửa này không thể làm hồi quy các
anh em `masking == 1`: chúng vốn không bao giờ là một phần của phép tính mask,
nên không có gì về chúng thay đổi. Đo lại sau sửa: 62% pixel nét viền được lấy
mẫu hiện màu của riêng `BellyTexture` (tăng từ 35%), thêm 22% nữa hợp pháp bị
che bởi các anh em `masking == 1` khác, không liên quan (quan hệ z-order của
chúng với `BellyTexture` được sửa này để yên một cách đúng đắn — đã xác nhận
bằng cách render lại với `Head_DarkBlue`/`Eye_Back`/`Head_DarkBlue 2`/
`Eye_Upper` bị gỡ khỏi cây hoàn toàn: số "bị che" còn lại gần như không đổi,
1063 px so với 1126 px, nên nó không đến từ các layer mục tiêu của sửa này chút
nào), và phần dư nhỏ nhất quán với anti-aliasing tại ranh giới mask hơn là một
lỗ thật.

Một nét viền source làm thon hoặc có cọ vẫn chỉ đóng góp hình bóng tô trần của
nó cho mask, giống như trước sửa này — hình học chưa được xác nhận cho hai
trường hợp đó. Xem phần MASKING trong docstring của module và KNOWN GAPS.

---

## 10. Trạng thái của `Exporter` và vì sao mỗi lần xuất một instance

`Exporter` cố ý là class **có trạng thái duy nhất** trong file. Trạng thái của
nó chia làm ba vòng đời:

| Vòng đời | Các trường | Ghi chú |
|---|---|---|
| **Mỗi lần xuất** | `_skin_cache`, `_next_id` | `_next_id` đặt tên các def `<mask>`/`<linearGradient>`/`<filter>`. Dùng chung một Exporter cho các lần xuất đồng thời sẽ đan xen các id và tạo ra các def tham chiếu chéo. |
| **Mỗi mesh layer** (đặt rồi xóa) | `_active_actions`, `_layer_scale` | Được đặt ngay trước khi render các shape của một layer, bị xóa ngay sau đó. Điểm xóa chính xác là điểm chịu lực — xem [§ 9.3](#93-điểm-lạ-của-ngữ-cảnh-smart-bone-rỗng). |
| **Mỗi lần xuất, chỉ thêm** | `_brush_asset_cache`, `_brush_defs`, `_brush_refs`, `_brush_tinted_defs`, `_brush_tinted_ids` | Được điền một cách lười *trong khi* phần body đang được render, đây là lý do `_wrap()` chỉ có thể thêm trước `<defs>` ở rất cuối. |

**Hãy xây một `Exporter` cho mỗi lần xuất** — hoặc cho mỗi goroutine trong một
bản port Go. Điều này được ghi trong docstring của class và là một ràng buộc
thật, không phải một gợi ý.

Một điều tinh tế về `<defs>`: `<mask>` và `<filter>` không bao giờ tự sơn,
nhưng một `<image>` trần thì có. Nên các ảnh cọ đã nhuộm sẵn **phải** được bọc
trong `<defs>`, nếu không mỗi ảnh tự sơn một lần tại `(x, y)` cục bộ của nó
trên tài liệu, ngoài mọi `<use>` của nó.

---

## 11. Tham chiếu chéo: trường → công đoạn tiêu thụ

Dùng cái này để nhảy từ một trường trong `moho-project-file-format.md` đến code
đọc nó.

| Trường | Được đọc bởi | Công đoạn |
|---|---|---|
| `project_data.width` / `.height` | `Document.from_raw`, `_to_pixel`, `_viewbox` | tải / chiếu pixel |
| `styles[]` | `StyleTable.build` | tải |
| `version` | `Document.format_version` | tải (được lưu, không bao giờ rẽ nhánh trên nó) |
| thứ tự `layers[]` | `Document.walk`, `emit` | thứ tự vẽ |
| `layer.visible`, `.edit_only` | `emit` | duyệt cây, bước (C) |
| `layer.name` | `emit`, `--layer`, `--mask-container` | duyệt cây / CLI |
| `layer.uuid` | `_resolve_patch_layers` | tải |
| `layer.type` (→ `.kind`) | `emit`, `export_layer` (→ `suppress_outline`); `build_deform_chain` (→ kiểm tra bone-layer); `emit` (→ kiểm tra switch-layer) | tải (phân loại kind) + render (nhiều điểm rẽ nhánh) |
| `layer.transforms.*` (5 trên 10) | `Layer.local_matrix` | transform |
| `layer.origin` | `Layer.local_matrix` | transform (trục xoay) |
| `layer.parent_bone` | `build_deform_chain` → `SkinStep` | skinning |
| `layer.flexi_bone_subset` | `_deformed_pixel_mapper` → `Skinner.deform` | skinning |
| `layer.group_mask` | `_mask_sources` | masking, bước (A) |
| `layer.masking` | `_mask_sources`, `_mask_source_shapes`, `member_clip` | masking |
| `layer.actions[].name` | `Layer.action_names` → `_active_smart_bones` | Smart Bones |
| `switch_keys` | `Layer.switch_active_child` | duyệt cây, bước (B) |
| `target_layer_uuid` | `_resolve_patch_layers` | tải |
| `mesh_layer` | `Layer._build` | tải (layer con được tổng hợp) |
| `mesh.points[].position` | `_curve_geometries` | hình học |
| `mesh.points[].width` | `_curve_geometries`, `_point_widths` | hình học + stroke width |
| `mesh.curves[].closed` | `CurveGeometry.build` | hình học |
| `curve_points[].point` | `CurveGeometry.build`, `_point_widths` | hình học |
| `curve_points[].smoothness`, `weight_*`, `offset_*` | `BezierReconstructor.handle` | hình học |
| `curve_points[].segments_on` | `SegmentGeometry.on` → `build_path_d(visible_only=True)` | chỉ path nét viền |
| thứ tự `shapes[]` | `ShapeGroupRenderer.render` | z-order trong một mesh |
| `shape.edges` | `PathTracer.trace`, `_point_widths` | truy path |
| `shape.has_fill` / `.has_outline` | `_render_shape` | chọn phần tử — `.has_outline` bị ghi đè thành `False` khi layer bao quanh là một `PatchLayer` (`suppress_outline`, § 7.6) |
| `shape.combo_mode` | `_render_shape`, `_flush` | các nhóm boolean |
| `shape.id`, `.name` | `_render_shape` (id phần tử, hạt giống cọ) | đặt tên đầu ra |
| `shape.effect_scale` / `.effect_rotation` | `_build_gradient` | vị trí gradient |
| `shape.style` + `inherited_style*` | `ResolvedStyle.resolve` | tải |
| `style.fill_color` / `line_color` | `_render_shape` | sơn |
| `style.line_width` | `_stroke_width_px` | stroke width |
| `style.line_caps` | `ResolvedStyle.line_cap_name` | `stroke-linecap` |
| `style.fill_style.*` | `_build_gradient` | def gradient |
| `style.brush_name` / `_jitter` / `_spacing` / `_align` / `_tint` | `_get_brush_asset`, `BrushStampOutliner.build` | đóng dấu cọ |
| `bone.name` | `_active_smart_bones` | khớp Smart Bone |
| `bone.parent` | `Skeleton.world_matrices` | phân cấp bone |
| `bone.length` | `Skinner.build` (`rest_p1`) | khoảng cách skinning |
| `bone.strength` | `Skinner.deform` (cổng + falloff) | trọng số skinning |
| `bone.anim_pos` / `anim_angle` / `anim_scale` | `Skeleton.world_matrices` | pose bone |
| channel `when` / `val` | `Channel.eval_raw` | mọi phép đánh giá |
| channel `actions[].pose` | `Channel.eval`, `frame_for_value` | Smart Bones |

Các trường **vắng mặt trong bảng này không được đọc chút nào.** Xem
`moho-project-file-format.md` § 13.2 cho những trường mà sự vắng mặt của chúng
thay đổi đầu ra một cách đo được, và § 13.3 cho các khoảng trống chưa kiểm
thử.

---

## 12. Thứ tự đọc cho người mới

Nếu bạn sắp thay đổi code này, hoặc port nó:

1. [§ 1](#1-tổng-quan-luồng-dữ-liệu) và [§ 3](#3-duyệt-cây-layer-thứ-tự-quyết-định)
   của tài liệu này — hình dạng của mọi thứ.
2. `moho-project-file-format.md` § 5–8 — dữ liệu thực sự là gì.
3. Các phần COORDINATES và STROKE WIDTH trong docstring của module — hai công
   thức mọi thứ khác đứng trên.
4. [§ 4](#4-transform-và-không-gian-tọa-độ) của tài liệu này — phần thật sự
   khó, và nơi một sự đơn giản hóa trông hợp lý là sai.
5. KNOWN GAPS trong docstring của module — trước khi bạn "sửa" bất cứ thứ gì.

Với một bản port Go cụ thể, phần PORTING NOTES trong docstring của module ánh
xạ mỗi banner `# ==== SECTION ====` trong `moho2svg.py` sang một file Go dự
định. Hai ràng buộc được mang theo và dễ bỏ sót: **một `Exporter` cho mỗi lần
xuất** ([§ 10](#10-trạng-thái-của-exporter-và-vì-sao-mỗi-lần-xuất-một-instance)),
và thiết kế accessor mỏng làm cho bộ cache định danh của `Channel.of` an toàn
([§ 5.1](#51-channelof-và-bộ-cache-định-danh)).
