# Moho to Lottie — thiết kế

> Bản dịch tiếng Việt của `docs/moho-to-lottie-design.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Thiết kế cho `moho2lottie.py`, một exporter thứ hai ghi một tài liệu Moho
thành một hoạt ảnh Lottie JSON, tái sử dụng pipeline hình học vốn đang cung
cấp sức mạnh cho `moho2svg.py`.

**Bản thiết kế này giờ đã được triển khai.** Toàn bộ 8 task trong
[`moho-to-lottie-plan.md`](moho-to-lottie-plan.md) đã hoàn thành, và
`moho2lottie.py` xuất thành công mọi tài liệu trong số 19 tài liệu mẫu của
repository này (đã kiểm chứng: hợp lệ theo schema, hình học được đối chiếu
với pipeline SVG tại nhiều frame cho mỗi tài liệu, đầu ra SVG byte-identical
không bị ảnh hưởng). Tài liệu này được giữ làm bản ghi thiết kế GỐC, không
được cập nhật từng dòng để khớp với triển khai cuối cùng ở mọi chi tiết —
nơi hai bên khác nhau, các ghi chú theo-task của chính tài liệu kế hoạch
giải thích điều gì đã thay đổi và vì sao (một số lỗi thật và vài phép đo sai
chỉ được tìm ra khi đã có code để kiểm tra trên các tài liệu thật). Hãy đọc
tài liệu kế hoạch để có các sự kiện hiện tại, đã kiểm chứng; hãy đọc tài
liệu này để hiểu lý luận đã định hình thiết kế trước khi bất kỳ phần nào của
nó được xây dựng. Nơi nào một phát biểu bên dưới là một phép đo, nó nói rõ
điều đó và đưa ra kích thước mẫu; nơi nào nó là một quyết định, nó nói rõ
điều gì đã được quyết định và vì sao; nơi nào nó chưa được kiểm chứng lúc
thiết kế, nó được liệt kê trong [§ 9](#9-các-câu-hỏi-mở) — hầu hết những mục
đó giờ đã được giải quyết, và tài liệu kế hoạch nói rõ cách thức.

Các tài liệu đồng hành:

- [`moho-to-lottie-plan.md`](moho-to-lottie-plan.md) — kế hoạch triển khai,
  bảng tiến độ riêng của nó, và những gì thực sự xảy ra theo từng task (kể
  cả các đính chính cho chính thiết kế của tài liệu này).
- [`lottie-and-thorvg.md`](lottie-and-thorvg.md) — chính định dạng Lottie,
  được đọc ra từ JSON Schema lưu trong `lottie/`.
- [`moho-export-pipeline.md`](moho-export-pipeline.md) — cách `moho2svg.py`
  duyệt một tài liệu ngày nay.
- [`moho-project-file-format.md`](moho-project-file-format.md) — tài liệu
  tham chiếu trường của Moho.
- [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md) —
  bones và skinning, phần mà Lottie không thể biểu diễn.

---

## 1. Mục tiêu và tiêu chí thành công

Xuất toàn bộ một tài liệu Moho thành **một file Lottie hoạt ảnh** chạy được
trong lottie-web.

Thành công nghĩa là tất cả những điều sau:

1. Với mọi frame trong khoảng của tài liệu, file Lottie vẽ cùng artwork mà
   `python3 moho2svg.py --combined --frame N` vẽ ngày nay. "Giống nhau" được
   kiểm bằng số, không phải bằng mắt — xem [§ 8](#8-kiểm-chứng).
2. Các SVG xuất ra vẫn byte-identical so với đầu ra trước refactor sau khi
   refactor dùng chung trong [§ 3](#3-các-thay-đổi-trong-moho2svgpy)
   (Makefile dựng chúng vào `out/svg/ori/`).
3. Đầu ra hợp lệ theo `lottie/lottie.schema.json`.
4. Không có dependency bên thứ ba bắt buộc mới.

Các mục ngoài mục tiêu được liệt kê trong [§ 2.2](#22-ngoài-phạm-vi-cho-v1).

---

## 2. Phạm vi

### 2.1 Trong phạm vi cho v1

| Tính năng | Vì sao rẻ hoặc cần thiết |
|---|---|
| `MeshLayer`, `GroupLayer`, `BoneLayer` | Lõi của mọi tài liệu. |
| Fill, stroke, opacity | Tương đương Lottie trực tiếp (`fl`, `st`, `ks.o`). |
| Biến dạng bone, Smart Bones | Được bake vào vị trí đỉnh; xem [§ 4](#4-quyết-định-flat-bake). |
| Tapered strokes | `moho2svg.py` đã chuyển những nét này thành một outline được tô, nên chúng đến như hình học thường. |
| `PatchLayer` | Đã được giải quyết thành một mesh trùng lặp lúc tải bởi `Document._resolve_patch_layers`. Không có gì thêm để làm. |
| Gradients | `SS_Gradient2` xuất hiện 1.196 lần trên 17 trong số 19 tài liệu mẫu. Lottie có `gf` / `gs`. |
| Masking | 162 layer mang một `masking` khác không, và 70 container mang `group_mask == 2`. Bỏ nó sẽ để artwork ẩn lộ ra, thứ là lỗi thấy được rõ nhất có thể. |
| `SwitchLayer` | 17 layer. Rẻ dưới mô hình flat-bake — xem [§ 6.3](#63-switch-layers). |

### 2.2 Ngoài phạm vi cho v1

| Tính năng | Lý do |
|---|---|
| Brush textures | Bị loại trừ tường minh. Lottie không có nét vẽ có texture; ánh xạ duy nhất là một raster image asset, thứ là phần tốn kém nhất của `moho2svg.py`. |
| `ImageLayer` | 15 layer trong một tài liệu. `moho2svg.py` đã bỏ chúng vì nó là exporter chỉ-vector. Thêm chúng nghĩa là một pipeline raster asset, cùng công việc mà brush textures đã bị loại trừ vì nó. |
| Kết hợp boolean của shape (`combo_mode`) | Chỉ **16 shape trong toàn bộ 19 tài liệu** dùng một giá trị khác không (14 intersect, 2 union), tất cả trong `Bandit.mohoproj`. Hỗ trợ của lottie-web cho phần tử merge `mm` kém. v1 vẽ những shape này với outline thường của chúng và ghi một cảnh báo nêu tên từng cái. |
| Smart Warp | **Chưa giải mã** ở bất kỳ đâu trong repository này, và không có tài liệu mẫu nào dùng nó. |
| `interp` easing | Chính `moho2svg.py` bỏ qua nó (nội suy monotone-cubic thay vì curve chưa được giải mã của riêng Moho). v1 kế thừa hành vi đó thay vì phân kỳ khỏi renderer mà nó được kiểm chứng đối chiếu. Cycle markers từng được liệt kê ở đây; giờ chúng được chính `Channel` giải mã và áp dụng, nên cả hai exporter đều cycle - xem `moho-animation-and-transform.md` § 3.4. |
| Vật lý rigid-body (`physics.enabled` với `physics.static == false`) | `moho2svg.py` đã bỏ qua physics, dựa trên giả định đã nêu rằng "không cái nào trong số chúng ảnh hưởng một xuất vector phẳng của một frame đơn" - đúng cho một frame đơn, nhưng không đúng cho một xuất Lottie hoạt ảnh: `BoneLayer` cấp cao nhất của chính `Bandit.mohoproj` là một vật thể physics động, và các channel keyframed của riêng nó (tất cả kết thúc trước frame 41-90) không giải thích được chuyển động trải khắp màn hình mà render của chính Moho hiển thị trên toàn khoảng frame 25-127 của nó. Không module nào chạy một mô phỏng physics, nên một layer bị ảnh hưởng render ở pose nghỉ trên mọi frame được lấy mẫu; v1 ghi một cảnh báo có đếm nêu tên từng cái thay vì thầm lặng tạo ra một layer trông như tĩnh. |

Mọi mục bị loại trừ phải tạo ra một **cảnh báo có đếm trên stderr**, không
phải sự im lặng. Một tính năng bị bỏ một cách thầm lặng bị người đọc tiếp
theo hiểu thành "được hỗ trợ".

### 2.3 Hai quy tắc thứ tự mà writer phải làm đúng

Lottie sơn mục **đứng trước** của một danh sách lên trên. Quy tắc đơn đó
phải được áp dụng ở *cả hai* cấp, và bỏ sót một trong hai là vô hình đối với
`tools/check_lottie_geometry.py`, thứ chỉ luôn so sánh thứ tự của writer với
kỳ vọng riêng của nó về thứ tự đó:

1. **Layers** — `_build_layers` đảo ngược `collected`, vì Moho liệt kê layers
   từ sau ra trước.
2. **Shapes trong một layer** — `_finalize_shapes` đảo ngược các khối shape,
   vì đúng lý do đó: `mesh.shapes[0]` là phần ở sau cùng. Điều này ban đầu bị
   bỏ sót, làm z-đảo ngược mọi layer nhiều shape trong khi giữ các layer một
   shape đúng — `kalca` của `SketchBone.animeproj` vẽ phần tô hông sáng của
   nó đè lên dải thắt lưng tối của chính nó, nên chỉ một trong hai màu từng
   thấy được, trong khi `ara-cizgi` một-shape bên cạnh trông ổn.

Liên quan, và được tìm ra cùng cách: shape fills và gradient fills phải đặt
`"r": 2` (**even-odd**), không phải `1` (non-zero). Moho luôn là even-odd, và
`moho2svg.py` viết `fill-rule="evenodd"` trên mọi shape fill. Với non-zero,
bất kỳ lỗ nào được dựng từ các subpath quấn ngược chiều bị bịt kín — đầu lâu
bên trong huy hiệu `rozet1` mất hai hốc mắt.

`mesh.shape_order` của chính Moho (một channel `String` chứa các id shape)
trông như một z-order nhưng **không phải** là một — nó là một registry id,
và thứ tự file của `mesh.shapes` vẫn là thứ tự vẽ. Nó khác thứ tự file trong
49 trên 614 mesh, nhưng trong 47 trong số đó nó tăng chặt trong khi thứ tự
file thì không, và sắp xếp lại theo nó phá vỡ việc nhóm `combo_mode`. Xem
`Mesh.draw_order()` và `moho-rigging-and-deformation.md` § 7.1 để có đầy đủ
bằng chứng. `SketchBone.animeproj` không bị ảnh hưởng theo hướng nào cả
(0/82), nên sửa lỗi thứ tự trên tự nó đứng vững.

---

## 3. Các thay đổi trong `moho2svg.py`

Hai thay đổi, cả hai nhỏ, cả hai được kiểm chứng bằng việc các SVG tham
chiếu vẫn byte-identical.

### 3.1 Trình dựng path thứ hai

`build_path_d()` biến hình học đã tru thành một chuỗi `d` SVG. Thêm
`build_path_bezier()` bên cạnh nó, nhận cùng các đối số và trả về một bezier
Lottie thay thế:

```python
{"v": [[x, y], ...], "i": [[dx, dy], ...], "o": [[dx, dy], ...], "c": bool}
```

Cả hai gọi cùng `PathTracer.trace(geometries, edges)`, nên hai writer không
thể bất đồng về thứ tự duyệt hoặc ranh giới subpath.

`i` và `o` của Lottie **tương đối với chính đỉnh của chúng**, nên với một
segment đã tru, phép chuyển đổi là `o = c1 - p0` trên đỉnh bắt đầu của
segment và `i = c2 - p1` trên đỉnh kết thúc của nó. Một đỉnh được chia sẻ bởi
hai segment lấy `o` của nó từ segment đi ra và `i` của nó từ segment đi vào.

### 3.2 Một bước duyệt cây dùng chung

`Exporter.export_document` hiện duyệt cây layer và dựng các chuỗi SVG trong
cùng một vòng lặp. Bước duyệt đó chứa các quyết định thật — visibility,
`edit_only`, con hoạt động của một switch layer, các mask source, khi nào đệ
quy — và một exporter thứ hai phải đưa ra mọi quyết định trong số đó một
cách giống hệt.

Tách bước duyệt thành một generator phát ra thứ cần vẽ, và để cả hai writer
tiêu thụ nó:

```python
def walk_render_tree(exporter, frame, include_hidden=False) -> Iterator[RenderItem]
```

`RenderItem` mô tả một thứ vẽ được: layer, các tổ tiên của nó, `geometries`
của nó, mapper `to_px` của nó, giá trị `masking` của nó, các mask source của
nó, và độ sâu của nó. `export_document` trở thành một consumer định dạng
SVG; writer Lottie trở thành consumer thứ hai.

**Điểm tinh tế duy nhất.** Các điểm đặt và xóa chính xác của
`Exporter._active_actions` là điểm chịu lực — xem
[`moho-export-pipeline.md`](moho-export-pipeline.md) § 9.3, "điểm lạ của ngữ
cảnh Smart Bone rỗng". Generator phải đặt và xóa nó tại đúng những khoảnh
khắc vòng lặp hiện tại làm. Đây là lý do phép kiểm byte-identical trong
[§ 8.1](#81-cổng-hồi-quy-svg) là một cổng chứ không phải một thứ cho đẹp.

---

## 4. Quyết định flat-bake

Lottie không có skeleton. Mọi biến dạng Moho áp dụng — bone skinning, các
pose Smart Bone, các transform tổ tiên — phải được giải quyết trước khi hình
học được ghi.

v1 giải quyết **toàn bộ**: các điểm của mỗi shape được ghi bằng pixel canvas
cuối cùng, đúng như `to_px` tạo ra chúng cho writer SVG.

Các hệ quả đều là những sự đơn giản hóa:

- Mọi layer Lottie có một **identity transform** (`ks` với anchor mặc định,
  position `[0, 0]`, scale `[100, 100]`, rotation `0`).
- Không có liên kết `parent` giữa các layer, nên không có sổ sách chỉ số
  layer.
- Không phân rã ma trận thành dạng anchor / position / scale / rotation /
  skew của Lottie, thứ là phần rắc rối nhất của bất kỳ thiết kế
  giữ-transform nào.
- `to_px` đã tạo ra pixel với y hướng xuống và gốc ở góc trên bên trái, thứ
  là **chính xác hệ tọa độ của Lottie**. Không có bước chuyển đổi, nên không
  có chỗ cho lỗi dấu ẩn nấp.

Cái giá là kích thước file, và nó đã được đo thay vì đoán. Lấy mẫu mọi
project trong `moho/` tại 8 frame với chuỗi biến dạng thật:

| Tài liệu | Frames | Shapes | Shapes chuyển động | Kích thước ước tính |
|---|---|---|---|---|
| `WhatIsBone.animeproj` | 227 | 203 | 150 | ~21,6 MB |
| `SketchBone.animeproj` | 124 | 192 | 139 | ~7,5 MB |
| `Bandit.mohoproj` | 87 | 112 | 112 | ~1,8 MB |

Các kích thước là JSON thô ở khoảng 60 byte mỗi đỉnh, trước gzip. Lottie
thường được phục vụ đã gzip, thứ thường cắt JSON dạng này đi ba đến năm lần.

Một shape mà các điểm không bao giờ chuyển động được ghi **một lần** như một
path tĩnh (`"a": 0`) thay vì mỗi frame một lần. Quy tắc đơn đó là thứ giữ
các con số trên trong khoảng một chữ số hoặc hai chữ số thấp megabyte: bake
mọi shape ở mọi frame bất kể sẽ tổng cộng khoảng 293 MB trên toàn bộ tập tài
liệu.

Một tối ưu hóa về sau có thể giữ các layer thuần-transform như các transform
keyframe Lottie và chỉ bake hình học đã skin, thứ đo được nhỏ hơn khoảng ba
đến chín lần trên toàn bộ tập tài liệu.
Đó là một thay đổi trong cùng writer, không phải một viết lại, và nó cố ý
không nằm trong v1.

---

## 5. Ánh xạ document và layer

### 5.1 Đối tượng gốc

`project_data` mang mọi thứ Lottie root cần:

| Trường Lottie | Nguồn | Ví dụ (`Bandit.mohoproj`) |
|---|---|---|
| `fr` | `project_data.fps` | `24.0` |
| `ip` | `project_data.start_frame` | `25` |
| `op` | `project_data.end_frame + 1` | `128` |
| `w` / `h` | `project_data.width` / `.height` | `1920` / `1080` |
| `v` | một chuỗi schema version cố định | — |

Các số frame của Moho là tuyệt đối và của Lottie cũng vậy, nên một tài liệu
bắt đầu ở frame 25 ghi keyframe đầu tiên của nó tại `t = 25`. Không có gì bị
đổi gốc, thứ loại bỏ cả một lớp lỗi lệch-một.

Việc `op` có loại trừ hay không là một suy luận, không phải một sự kiện đã
xác nhận — xem [§ 9](#9-các-câu-hỏi-mở).

### 5.2 Layers

Mỗi mesh layer Moho trở thành một shape layer Lottie (`"ty": 4`) với một
`ks` identity, một `ind` tuần tự, và không có `parent`.

**Thứ tự vẽ bị đảo ngược.** Moho vẽ danh sách layer của nó từ sau ra trước,
thứ tự mà `Document.walk()` phát ra. Lottie vẽ **layer đầu tiên trong danh
sách lên trên**. Danh sách được xuất ra vì vậy là phép đảo ngược của thứ tự
duyệt.

Đây là lỗi thầm lặng có khả năng xảy ra nhất trong toàn bộ thiết kế: đầu ra
vẫn trông như đúng artwork, chỉ là những thứ sai nằm ở phía trước. Nó có một
bước được đặt tên riêng trong writer và một phép kiểm riêng trong
[§ 8.2](#82-phép-kiểm-tương-đương-hình-học).

### 5.3 Shapes

Mỗi shape Moho trở thành một group (`"ty": "gr"`) trong danh sách `shapes`
của layer, chứa, theo thứ tự:

1. `"ty": "sh"` — path, từ `build_path_bezier()`.
2. Một fill: `"ty": "fl"` cho một màu đặc, `"ty": "gf"` cho một gradient.
3. Một stroke: `"ty": "st"`, với `w` lấy từ cùng `stroke_width_px` mà writer
   SVG dùng, và `lc` / `lj` từ style đã giải quyết.
4. `"ty": "tr"` — group transform, identity.

Một shape không fill bỏ qua bước 2; một shape không outline bỏ qua bước 3.

Path tĩnh và path hoạt ảnh chỉ khác nhau ở property envelope:

```json
"ks": {"a": 0, "k": {"v": [], "i": [], "o": [], "c": true}}
"ks": {"a": 1, "k": [{"t": 25, "s": [{"v": [], "i": [], "o": [], "c": true}]},
                      {"t": 26, "s": [{"v": [], "i": [], "o": [], "c": true}]}]}
```

Path keyframes chỉ có thể được nội suy khi mọi keyframe có cùng số đỉnh và
cấu trúc subpath. **Điều này đã được đo và giữ vững**: trên 2.659 shape trong
18 tài liệu tải được, lấy mẫu 12 frame mỗi cái, **không** shape nào thay đổi
cấu trúc. Hai lý do độc lập hỗ trợ điều này:

- `combo_mode` không bao giờ làm thay đổi hình học. Kết hợp boolean được
  triển khai như các mask SVG đè lên các path theo-shape không bị đụng tới
  (`ShapeGroupRenderer._flush`), không phải như một boolean hình học, nên
  không có đỉnh nào được tạo hoặc bị gỡ.
- `segments_on`, trường duy nhất có thể tách một path thành nhiều subpath
  hơn, **không bao giờ được hoạt ảnh**: 53.027 instance trên toàn bộ 19 tài
  liệu, không cái nào có hơn một keyframe.

Writer vẫn phải khẳng định điều này cho từng shape và thất bại một cách ầm ĩ
nếu một tài liệu bao giờ vi phạm nó, thay vì xuất ra một file mà player sẽ
render thành rác.

---

## 6. Ba vùng tính năng

### 6.1 Masking

Moho biểu diễn masking bằng hai trường: `group_mask` của một container, và
`masking` riêng của mỗi con. `moho2svg.py` giải quyết chúng trong
`Exporter._mask_sources`, thứ trả về các path tạo nên mask, và coi
`masking in (1, 2)` là được miễn trừ (được vẽ không bị cắt).

Lottie cung cấp hai cơ chế. v1 dùng cái đơn giản hơn:

**Đã chọn: `masksProperties` theo-layer.** Mọi layer bị mask mang bản sao
riêng của mask, như một danh sách các mục mask với `mode: "a"` (add, nên
nhiều source hợp lại) hoặc `mode: "s"` (subtract). Vì hình học đã được
flat-bake thành pixel canvas và mọi transform layer là identity, các path
mask không cần điều chỉnh gì cả — chúng là cùng tọa độ mà `<mask>` SVG dùng.

**Đã bác bỏ: track matte cộng precomposition.** Một track matte Lottie áp
cho đúng một layer, nên mask một nhóm anh em nghĩa là chuyển chúng vào một
precomposition asset và áp matte cho layer precomp. Đó là nhiều cấu trúc hơn,
nhiều sổ sách chỉ số hơn, và nhiều thứ có thể sai hơn, mà không có lợi ích
gì trong phạm vi của v1. Nó vẫn được ghi lại ở đây làm phương án dự phòng
nếu mask theo-layer hóa ra render không đúng.

Cái giá của phương án đã chọn là sự trùng lặp: N anh em bị mask mang N bản
sao của hình học mask. Các path mask thường nhỏ, và phép đo kích thước trong
[§ 4](#4-quyết-định-flat-bake) bị thống trị bởi hình học shape, không phải
mask.

**Khiếm khuyết kế thừa.** `moho2svg.py` có một trường hợp đã biết-sai cho
các anh em `masking == 2`, được ghi chi tiết trong `Exporter.export_document`
và trong phần MASKING của docstring module: stroke của một anh em như thế
nên vẫn thấy được trên những gì nó mask, và hiện vẽ ở vị trí danh sách thường
của nó. v1 tái tạo hành vi hiện tại thay vì phân kỳ. Sửa nó thuộc về writer
SVG trước, nơi có một xuất tham chiếu để đối chiếu.

### 6.2 Gradients

`SS_Gradient2` ánh xạ sang `gf` (gradient fill) và `gs` (gradient stroke)
của Lottie:

| Lottie | Moho |
|---|---|
| `t: 1` linear / `t: 2` radial | `fill_style.gradient_type` 0 / 1 |
| `g.p` | số stop |
| `g.k` | các stop làm phẳng thành `[offset, r, g, b, ...]` từ `gradients[].location` và `.color` |
| `s` / `e` | điểm bắt đầu và kết thúc, lấy từ cùng hình học mà writer SVG tính cho `<linearGradient>` / `<radialGradient>` |

Độ chính xác vị trí gradient là một KNOWN GAP sẵn có trong `moho2svg.py`
(`effect_scale` / `effect_rotation`). v1 tái sử dụng bất cứ thứ gì writer SVG
tính, nên cả hai exporter sai theo cùng một cách thay vì khác nhau. Cải
thiện vị trí là một task riêng đối chiếu với đầu ra tham chiếu SVG.

### 6.3 Switch layers

Một `SwitchLayer` hiển thị đúng một con tại một thời điểm, được chọn bởi
`Layer.switch_active_child(frame, exporter)`. Channel chứa các chuỗi, thứ
bám vào keyframe bên trái mà không nội suy, nên con hoạt động thay đổi tại
các frame rời rạc và mỗi con hoạt động trên một hoặc nhiều **cửa sổ frame
liền nhau**.

Mỗi cửa sổ trở thành một layer được xuất với `ip` và `op` được đặt cho cửa
sổ đó. Một con hoạt động trong hai cửa sổ tách biệt được xuất hai lần. Không
có mánh khóe opacity, không có logic chuyển đổi theo-frame trong player.

---

## 7. Cảnh báo và sự trung thực lúc chạy

Writer giữ một bộ đếm cho mỗi tính năng bị bỏ qua và in một bản tóm tắt ra
stderr ở cuối một lần xuất:

```
moho2lottie: N shapes with combo_mode != 0 drawn without boolean combination
moho2lottie: N ImageLayer layers skipped (vector-only exporter)
moho2lottie: N styles naming a brush drawn as plain strokes
```

Mỗi `N` được đếm trong tài liệu đang được xuất. Các con số trên toàn tập tài
liệu được trích dẫn ở nơi khác trong tài liệu này không phải là thứ một lần
xuất đơn lẻ báo cáo.

---

## 8. Kiểm chứng

Không có test suite trong repository này, và không có Lottie player nào được
cài. Kế hoạch vì vậy dựa vào các phép kiểm không cần cả hai.

### 8.1 Cổng hồi quy SVG

Sau khi tách `walk_render_tree` trong [§ 3.2](#32-một-bước-duyệt-cây-dùng-chung),
các SVG xuất ra phải giữ **byte-identical** so với đầu ra trước khi tách. Đây
là một cổng mạnh: nó luyện tập bước duyệt đầy đủ, kể cả thứ tự ngữ cảnh
Smart Bone, trên năm tài liệu thật. (Cổng này lúc đó chạy bằng `make gen`;
Makefile hiện dựng cùng các SVG đó vào `out/svg/ori/` bị gitignore.)

### 8.2 Phép kiểm tương đương hình học

Phép kiểm tính đúng đắn chính không cần player và không cần dependency.

Với một tài liệu và một frame, exporter có thể tạo ra cả hai đầu ra từ cùng
hình học đã tru. Một checker sau đó:

1. đọc mọi path keyframe tại frame N ra khỏi file Lottie đã xuất;
2. chuyển mỗi cái trở lại các điểm điều khiển tuyệt đối (`c1 = v + o`,
   `c2 = v_next + i_next`);
3. render cùng tài liệu tại frame N qua `build_path_d()`;
4. so sánh hai chuỗi tọa độ trong một dung sai nhỏ.

Bất kỳ bất đồng nào là một lỗi thật trong writer, được tìm ra mà không render
gì cả. Điều này cũng bắt được lỗi thứ-tự-vẽ-đảo-ngược từ
[§ 5.2](#52-layers), vì phép kiểm duyệt các shape theo thứ tự đã xuất.

### 8.3 Xác thực schema

Xác thực đầu ra theo `lottie/lottie.schema.json`. Điều này cần package
`jsonschema`, thứ là **tùy chọn** theo cùng cách Pillow đã là: nếu nó import
được, hãy xác thực; nếu không, in một ghi chú và bỏ qua. Không có dependency
bắt buộc nào được thêm.

Chú ý lời cảnh báo từ [`lottie-and-thorvg.md`](lottie-and-thorvg.md) § 2.5:
vượt qua schema không phải là bằng chứng của một file đúng, vì schema đánh
dấu rất ít thứ là bắt buộc.

### 8.4 Xác nhận trực quan

Điều duy nhất các phép kiểm trên không thể làm là chứng minh rằng lottie-web
*render* file như dự định — đặc biệt là quy tắc thứ tự shape-element, thứ mà
[`lottie-and-thorvg.md`](lottie-and-thorvg.md) § 6.4 ghi chú là không thể
biểu diễn trong schema chút nào.

Một trang xem trước nhỏ tải một bản build `lottie-web` được vendor cục bộ,
hiển thị hoạt ảnh bên cạnh SVG của `moho2svg.py` tại cùng frame, khép khoảng
trống đó. Player được vendor bị gitignore, giống như `out/` và `moho/`.

### 8.5 Make targets

- `make lottie-all` — xuất mọi project dưới `moho/` vào `out/lottie/`
  (bị gitignore).
- `make check-lottie` — dựng các lần xuất lottie của các project mẫu rồi
  chạy phép kiểm tương đương hình học của
  [§ 8.2](#82-phép-kiểm-tương-đương-hình-học) trên một mẫu các frame.

---

## 9. Các câu hỏi mở

Được sắp xếp theo mức chúng có thể thay đổi công việc. Trạng thái được thêm
sau khi triển khai; xem `moho-to-lottie-plan.md` cho task đã giải quyết từng
mục, nơi nào có một task như thế.

1. **`op` của Lottie có loại trừ không?** [§ 5.1](#51-đối-tượng-gốc) giả định
   `end_frame + 1`. Nếu nó bao gồm, mọi lần xuất dài đúng một frame. Rẻ để
   giải quyết đối chiếu với một player, và rẻ để sửa. **Vẫn mở** — không có
   Lottie player nào được dùng ở bất kỳ đâu trong project này; lựa chọn
   `end_frame + 1` của chính `moho2lottie.py` chưa được kiểm chứng. Cũng
   được liệt kê là mở trong phần "Sau kế hoạch" của chính tài liệu kế hoạch.
2. **Thứ tự shape element bên trong một group.** "Một style áp cho các shape
   lân cận" không phải một quy tắc kiểm-máy-được và không nằm trong schema.
   Thứ tự trong [§ 5.3](#53-shapes) là thứ tự quy ước, chưa được kiểm chứng
   ở đây. **Né tránh, không giải quyết**: Task 3 cho mỗi shape tối đa hai
   group Lottie TÁCH BIỆT (một cho fill, một cho outline) thay vì một group
   trộn cả hai toán tử vẽ, cụ thể là để sự mơ hồ này không thể ảnh hưởng kết
   quả theo hướng nào. Vẫn mở cho bất kỳ ai xây một writer cần ít group hơn,
   phức tạp hơn.
3. **`masksProperties` theo-layer có tái tạo masking của Moho không?** Phương
   án dự phòng (track matte cộng precomposition) đã được thiết kế nhưng chưa
   được chi tiết. **Đã triển khai theo-layer, hình học đã được kiểm, tính
   đúng đắn trực quan vẫn mở**: Task 6 xây nó (với hình học mask được
   keyframe theo từng frame, một khoảng trống thật mà thiết kế này không
   lường trước - mask chuyển động nhiều như bất kỳ shape nào khác) và xác
   nhận hình học đã xuất khớp trực tiếp với pipeline; việc nó có cắt đúng
   trong một Lottie player thật hay không chưa được kiểm chứng, cùng nguyên
   nhân gốc với mục 1. Một sự đơn giản hóa có chủ đích, có đếm: khoản
   loại-trừ-stroke của phía SVG (outline riêng của một mask source vẫn thấy
   được trên những gì nó cắt) không được tái tạo - mô hình mask của Lottie
   không có primitive "stroke as mask", và nó là một hiệu ứng hẹp (16 trên
   180 shape mask source, 9%, được đo trực tiếp).
4. **Khiếm khuyết `masking == 2` của `Bandit.mohoproj` có tệ hơn trong Lottie
   so với SVG không?** Thứ tự đã biết-sai của writer SVG được kế thừa có chủ
   đích; mức độ thấy được của nó trong một Lottie player là không rõ. **Vẫn
   mở** — cùng nguyên nhân gốc với mục 1.
5. **Kích thước gzip của đầu ra lớn nhất.** `WhatIsBone.animeproj` ở ~21,6 MB
   thô là trường hợp xấu nhất đã đo. Nếu gzip không đưa nó vào một khoảng
   chấp nhận được cho phân phối web, tối ưu hóa giữ-transform từ
   [§ 4](#4-quyết-định-flat-bake) chuyển từ "sau này" thành "bắt buộc".
   **Đã giải quyết: gzip là đủ, không cần thêm việc gì.** Đầu ra thực tế của
   exporter hoàn chỉnh cho `WhatIsBone.animeproj` là 23,9 MB thô (cao hơn
   ước tính này, vì nó bao gồm masking và gradients hoạt động mà ước tính này
   không mô hình hóa) nhưng chỉ **2,4 MB khi gzip** (~10x) — phân phối web
   thoải mái. Tối ưu hóa giữ-transform vẫn là một cải tiến SAU NÀY khả thi,
   không phải một cải tiến bắt buộc.
6. **Một bản tiếng Việt của tài liệu này** dưới `docs/localization/` chưa
   được viết. Nó cố ý bị hoãn: đây là một thiết kế sẽ thay đổi trong lúc triển
   khai, và dịch một mục tiêu đang chuyển động hai lần là phí phạm. **Vẫn bị
   hoãn.** Thiết kế không còn là một mục tiêu đang chuyển động nữa giờ khi
   việc triển khai đã xong, nên việc này có thể được bắt tay vào, nhưng làm
   vậy nằm ngoài phạm vi của chính công việc triển khai và không được yêu
   cầu.

---

## 10. Những gì đã được đo cho tài liệu này

Mọi con số được trích dẫn ở trên đến từ một script chạy trên các file trong
`moho/`, không phải từ một ước tính. Bốn phép dò là:

| Phép đo | Kết quả | Mẫu |
|---|---|---|
| Tính ổn định số đỉnh path qua các frame | 0 không ổn định | 2.659 shape, 18 tài liệu, 12 frame mỗi cái |
| `segments_on` từng được hoạt ảnh | không bao giờ | 53.027 instance, 19 tài liệu |
| Shapes chuyển động, với chuỗi biến dạng thật | 0% đến 100% mỗi tài liệu | 19 tài liệu, 8 frame mỗi cái |
| Các đếm `combo_mode`, `masking`, `group_mask`, gradient và loại layer | xem [§ 2](#2-phạm-vi) | 19 tài liệu |

Một tài liệu, `Rabbit.animeproj`, không thể tải được chút nào trong lúc các
phép đo này chạy; điều đó từ đó đã được sửa, và nó bị loại khỏi con số ổn
định trên thay vì thầm lặng được tính là vượt qua.
