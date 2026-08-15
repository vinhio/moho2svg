# Định dạng file dự án Moho

> Bản dịch tiếng Việt của `docs/moho-project-file-format.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Một file dự án Moho (`.mohoproj` cho Moho Pro, `.animeproj` cho Moho Debut)
là JSON thuần, dù tên file không nói vậy. Định dạng **không được Smith Micro /
Lost Marble tài liệu hóa chính thức**; mọi thứ bên dưới được tác giả của
`moho2svg.py` dịch ngược ra, bằng cách so sánh trên thực nghiệm đầu ra của
công cụ này với các file SVG do chính Moho xuất ("File > Export Animation"),
qua nhiều rig và hai phiên bản Moho (14.3 và 14.4).

Tài liệu này là bản tóm tắt dễ đọc của công việc dịch ngược đó.
**Nguồn có thẩm quyền cho các công thức render là module docstring ở đầu
`moho2svg.py`**, nơi còn ghi lại, cho mỗi công thức và hằng số, *cách* nó
được suy ra và *bằng chứng* nào hỗ trợ nó (kích thước mẫu, biên sai số, phần
nào là xác nhận-chính-xác so với heuristic khớp-tốt-nhất). Đọc docstring đó
trước khi sửa bất kỳ logic nào tài liệu này mô tả — vài thứ trông như lỗi được
cố ý giữ lại vì chúng khớp đầu ra thật của Moho.

Tài liệu này mô tả **cái gì nằm trong file**. Để biết **các trường này được
dùng thế nào lúc xuất** — thứ tự xử lý, quan hệ giữa layers, transforms,
bones, masking và styles, và công đoạn nào đọc trường nào — xem
`moho-export-pipeline.md`.

---

## 1. Phạm vi và cơ sở bằng chứng

Mọi danh sách trường, tập giá trị và số đếm trong tài liệu này được đo bằng
cách duyệt các file dự án trong thư mục (bị gitignore) `moho/`. Mẫu đó nhỏ,
nên hãy coi "các giá trị duy nhất quan sát thấy" là *bằng chứng*, không phải
*tập đầy đủ mà định dạng cho phép*.

Mẫu được mở rộng giữa chừng vòng đời của tài liệu này từ 5 file ban đầu lên
**19**, thêm các tài liệu hướng dẫn công cụ bone đi kèm của chính Moho
(`AnglePositionScale`, `BoneDynamics`, `BoneParenting`, `BoneStrengthTool`,
`ControlBones`, `IK-FK`, `IndependentAngle`, `MaximumIKStrethching`,
`OffsetBoneTool`, `Rabbit`, `SelectandReparentBoneTool`, `TargetBone`,
`TransformBoneTool`, cộng `SlickObjectTransition`). Những phát hiện chỉ lộ ra
khi quét rộng 19 file thì được đánh dấu **(phát hiện từ 19 file)** dưới đây,
để phân biệt rõ nhận định nào dựa trên bằng chứng 5 file ban đầu, nhận định
nào cần mẫu lớn hơn. Bản đối chiếu máy đọc được của tài liệu này — một JSON Schema đã
validate với cả 19 file, kèm bản rà soát mức độ bao phủ
riêng — nằm trong `schema/`; xem `schema/README.md`.

| Tài liệu | `version` | Canvas | Frames | Layers | Named styles |
|---|---|---|---|---|---|
| `AddBone.animeproj` | 1038 | 1280×720 | 1–25 | 229 | 201 |
| `ReparentBone.animeproj` | 1038 | 1280×720 | 1–120 | 42 | 201 |
| `SketchBone.animeproj` | 1038 | 1280×720 | 1–120 | 108 | 239 |
| `WhatIsBone.animeproj` | 1038 | 1280×720 | 1–240 | 140 | 118 |
| `Bandit.mohoproj` | 1045 | 1920×1080 | 25–127 | 25 | 12 |
| `AnglePositionScale.animeproj` | 1038 | 1280×720 | 1–120 | 10 | 273 |
| `BoneDynamics.animeproj` | 1038 | 1280×720 | 1–29 | 14 | 273 |
| `BoneParenting.animeproj` | 1038 | 1280×720 | 1–120 | 10 | 273 |
| `BoneStrengthTool.animeproj` | 1038 | 1280×720 | 1–25 | 22 | 201 |
| `ControlBones.animeproj` | 1038 | 1280×720 | 1–120 | 25 | 240 |
| `IK-FK.animeproj` | 1038 | 1280×720 | 1–120 | 10 | 273 |
| `IndependentAngle.animeproj` | 1038 | 1280×720 | 1–120 | 45 | 273 |
| `MaximumIKStrethching.animeproj` | 1038 | 1280×720 | 1–120 | 45 | 273 |
| `OffsetBoneTool.animeproj` | 1038 | 1280×720 | 1–120 | 25 | 201 |
| `Rabbit.animeproj` | **1021** | 1920×1080 | 1–29 | 17 | 0 |
| `SelectandReparentBoneTool.animeproj` | 1038 | 1280×720 | 1–120 | 42 | 201 |
| `SlickObjectTransition.mohoproj` | 1038 | 1280×720 | 1–96 | 7 | 0 |
| `TargetBone.animeproj` | 1038 | 1280×720 | 1–120 | 45 | 273 |
| `TransformBoneTool.animeproj` | 1038 | 1280×720 | 1–120 | 15 | 239 |

(Số đếm layer bao gồm `MeshLayer` lồng bên trong mỗi `TextLayer`. `fps` là
`24.0` trong mọi mẫu, nên nó bị bỏ khỏi bảng này.)

Tổng cộng qua 19 tài liệu: 876 layers (trong đó 648 `MeshLayer`, 103
`GroupLayer`, 47 `BoneLayer`, 34 `TextLayer`, 17 `SwitchLayer`, 15
`ImageLayer` **(phát hiện từ 19 file — [§ 6.1](#61-các-loại-layer))**, 12
`PatchLayer`), 3.764 named styles, 2.660 shapes, 3.045 curves, 52.748 mesh
points, 53.027 curve points, 850 bones, và 584.616 animation channels
(423.642 `Val`, 72.646 `Color`, 68.903 `Vec2`, 14.896 `Bool`, 2.812 `Vec3`,
1.717 `String`). Một tài liệu cũng có thể mang **không** named style nào cả
(`Rabbit`, `SlickObjectTransition` **(phát hiện từ 19 file)**).

Ba giá trị `version` giờ được lấy mẫu, và chúng hành xử khác nhau ở vài chỗ
(styles, các trường theo điểm, `combo_mode`). Khắp tài liệu này, **"cũ nhất"**
nghĩa là `version 1021` của `Rabbit.animeproj` **(phát hiện từ 19 file)**,
**"cũ hơn"** nghĩa là các tài liệu `1038` (17 trong 19), và **"mới hơn"** nghĩa
là tài liệu `1045` duy nhất (`Bandit.mohoproj`) — vẫn chỉ một file, nên một kết
luận rút riêng từ nó nằm trên đúng một file đó.

---

## 2. Cấu trúc cấp cao nhất

```jsonc
{
  "version": 1045,
  "project_data":    { "width": 1920, "height": 1080, ... },
  "styles":          [ { "type": "Style", "name": "...", "uuid": "...", ... } ],
  "layers":          [ { "type": "BoneLayer", "name": "...", "layers": [...] } ],
  "animated_values": { "camera_zoom": { ...channel... }, ... },
  "layercomps":      [],
  "action_refs":     []
}
```

Mọi khóa cấp cao nhất quan sát thấy, và `moho2svg.py` có đọc nó không:

| Khóa | Loại | Ý nghĩa | Được dùng? |
|---|---|---|---|
| `layers` | list | Cây layer của tài liệu ([§ 6](#6-layers)). Quan sát thấy 1–4 root layers. | **có** |
| `styles` | list | Danh sách named style toàn tài liệu ([§ 8](#8-styles)). | **có** |
| `project_data` | obj | Canvas và cài đặt render ([§ 3](#3-project_data)). | một phần — chỉ `width`/`height` |
| `version` | int | Bản sửa đổi định dạng: `1021` (cũ nhất được mẫu), `1038` (đa số), hoặc `1045` (mới nhất được mẫu) **(1021 là phát hiện từ 19 file)**. | **có** — được đọc, nhưng không nhánh nào phụ thuộc vào nó |
| `animated_values` | obj | Các channel cấp tài liệu: camera + timeline markers ([§ 5.5](#55-animated_values-cấp-tài-liệu)). | không |
| `layercomps` | list | Layer comps (các tập show/hide đã lưu). **Rỗng trong cả 19 tài liệu**, nên hình dạng phần tử của nó chưa biết. | không |
| `action_refs` | list | **Rỗng trong mọi tài liệu có khóa này**, nên hình dạng phần tử của nó chưa biết. Chắc là tham chiếu tới các action trong tài liệu ngoài/liên kết; xem [§ 11.4](#114-action_refs-và-layercomps). Vắng hẳn trong tài liệu `1021` — xem hàng dưới. | không |
| `major_version` / `rev_version` | int | Luôn `1` / `0`. | không |
| `mime_type` | str | Luôn `"application/x-vnd.lm_mohodoc"`. | không |
| `doc_uuid` | str | Nhận dạng tài liệu. | không |
| `created_date` / `modified_date` | str | Dấu thời gian đọc được, ví dụ `"Wed Aug 31 16:17:24 2016"`. | không |
| `comment` | str | Chỉ trong các file thế hệ mới: `"Created in Moho version 14.3, ..."`. | không |
| `thumbnail` | str | Chỉ trong các file thế hệ mới: ảnh xem trước base64 JPEG. | không |
| `documentviewstate` | obj | Đúng 48 khóa `DocState_*` của editor trong mọi file trong cả 19 tài liệu (zoom, grid, playback range, viewport split, camera ngoài view theo từng góc phần tư) **(toàn bộ liệt kê 48 khóa là phát hiện từ 19 file — xem `DocumentViewState` trong `schema/project.schema.json`)**. Trạng thái UI thuần, không ảnh hưởng hình học xuất ra. | không |
| `metadata` | obj | Túi khóa/giá trị nhỏ: `what` (`0`), `save_time` (`1` — không phải dấu thời gian dù tên như vậy), `layerwnd_searchcontext` **(hai cái sau là phát hiện từ 19 file)**. | không |
| `onions_*` (14 khóa) | mixed | Cài đặt editor onion-skin. Các khe frame chưa đặt là `-100000`. | không |

**Thế hệ định dạng `1021` (`Rabbit.animeproj`) bỏ hẳn `doc_uuid`, `action_refs`
và `modified_date` — không phải là các giá trị rỗng, mà các khóa vắng mặt
hoàn toàn khỏi JSON (phát hiện từ 19 file).** Nó cũng có không named style
(`styles: []`), thứ các thế hệ `1038`/`1045` không bao giờ có. Bất cứ điều gì
trong tài liệu này nói một trường "luôn hiện diện" ngầm loại trừ thế hệ duy
nhất này trừ khi có ghi chú khác.

**Không gì trong tài liệu là chỉ số z-order.** Thứ tự vẽ (sau ra trước) đơn
giản là thứ tự các layer xuất hiện trong `layers`, đệ quy, và thứ tự các shape
xuất hiện trong `mesh.shapes`.

**Bảng Layer Pool của chính ứng dụng Moho hiển thị các con của một container
theo thứ tự *ngược* với thứ tự mảng `layers` này** — hàng đầu của bảng là
phần tử *cuối* của mảng, và ngược lại. Đây là một sự thật hiển thị UI đã xác
nhận, nhưng nó **không** phải bằng chứng rằng thứ tự của mảng `layers` là
"ngược" cho mục đích render: một bảng layers hiển thị trước-nhất-ở-trên trong
khi mảng bên dưới lưu sau-ra-trước là một quy ước UI thường, không liên quan
đến thứ tự vẽ. Đã kiểm tra trực tiếp: đảo ngược toàn bộ mảng `layers` trước
khi vẽ đã được thử với container gốc `Bandit` của `Bandit.mohoproj` và tạo
đầu ra sai thấy rõ — nó lật quan hệ vốn đúng, nơi `Muzzle`/`Nose`/`EyeBrow`
(`masking == 1`) vẽ bình thường trên `BellyTexture`, kéo lớp tô đặc của
`BellyTexture` phủ lên mắt/mõm/mũi của nhân vật (đã xác nhận sai so với chính
ứng dụng Moho: ba layer đó vẫn không bị ảnh hưởng ở đó). Nên: thứ tự `layers`
**là** thứ tự vẽ sau-ra-trước, đúng như công cụ này vốn giả định — chỉ riêng
*hiển thị của bảng* chạy ngược chiều. Xem phần MASKING của module docstring
để có toàn bộ cuộc điều tra đã sinh ra điều này (một lỗi masking thật, tách
biệt, nay đã sửa).

---

## 3. `project_data`

Chỉ `width` và `height` được dùng. Phần còn lại được ghi lại ở đây để rõ cái
gì đang bị bỏ qua.

| Trường | Các giá trị quan sát thấy | Ý nghĩa |
|---|---|---|
| `width` / `height` | `1280×720`, `1920×1080` | Kích thước canvas theo pixel. **Được dùng** — xem [§ 4](#4-hệ-tọa-độ). |
| `fps` | `24.0` | Tốc độ frame. Không dùng: `--frame N` nhận một số frame, không phải một thời điểm. |
| `start_frame` / `end_frame` | `1`/`25`, `25`/`127`, `1`/`120`, `1`/`240` | Phạm vi hoạt ảnh. Chú ý `start_frame` không phải lúc nào cũng `0`, trong khi mặc định `--frame` của công cụ này *là* `0`. |
| `back_color` | `{r:234, g:234, b:234, a:255}` | Nền canvas. **Số nguyên 0–255**, khác với màu style ([§ 5.2](#52-các-loại-channel-và-hình-dạng-phần-tử-val)). Không được vẽ — SVG xuất ra có nền trong suốt. |
| `antialiasing` | `true` | Cờ render. |
| `depth_sort` / `distance_sort` | `false` | Sắp xếp 3D của các layer. |
| `depth_of_field`, `focus_distance`, `focus_range`, `focus_blur` | `false`, các số | Độ sâu trường ảnh của camera. |
| `noise_grain`, `pixelation` | `0.0` | Các effect render toàn cục. |
| `stereo_mode`, `stereo_separation` | `0`, số | Đầu ra stereo. |
| `global_render_style_fill_style`, `..._line_style`, `..._layer_style` | int (`0` trong mọi file của cả 19 tài liệu được mẫu) | Một override style toàn tài liệu áp dụng lúc render. **Đính chính:** một bản sửa cũ của tài liệu này báo các trường này là chuỗi rỗng trong mẫu 5-file; kiểm tra trực tiếp JSON thô cho thấy giá trị thật là **số nguyên `0`**, trong cả 5 file ban đầu, không phải `""`. `schema/project.schema.json` gõ trường này là `["string", "integer"]` chính vì *tập giá trị định dạng này cho phép* chưa được biết là đóng tại `0` — nếu một tài liệu từng đặt giá trị khác không, công cụ này sẽ bỏ qua nó và có thể tạo màu sai thấy rõ. |
| `global_render_style_minimize_randomness` | bool | Cùng họ override. `false` khắp nơi. |
| `color_palette` | `"Basic Colors.png"` | Palette swatch của editor. |
| `soundtrack` | str | Tham chiếu file âm thanh. |
| `extra_swf_frame`, `display_quality` | bool, int | Các tùy chọn xuất kế thừa. |

---

## 4. Hệ tọa độ

Điểm, translations, vị trí bone và độ dài bone đều được lưu trong một đơn vị
không gian tài liệu nơi **2 đơn vị trải hết chiều cao canvas** — tức là
`y = +1` là cạnh trên và `y = -1` là cạnh dưới, bất kể độ phân giải pixel.
Chiều rộng *không* được chuẩn hóa, nên phạm vi x thấy được phụ thuộc tỷ lệ
khung hình.

```
pixel_x = moho_x * (height / 2) + width / 2
pixel_y = height / 2 - moho_y * (height / 2)        # y is flipped
```

Góc ở đâu cũng tính bằng **radian** (bone angles, `rotation_z`, `brush_jitter`,
`offset_in`/`offset_out`). Các thành phần màu là float trong `0.0–1.0` bên
trong channels, nhưng là số nguyên `0–255` trong một số trường màu thường
(không phải channel) như `project_data.back_color` và các màu `TextLayer`.

---

## 5. Các giá trị hoạt ảnh (channels)

Hầu như mọi thuộc tính số, màu, boolean hoặc chuỗi trong Moho được lưu dưới
dạng cùng một đối tượng "channel". Đây là cấu trúc lặp lại nhiều nhất trong
định dạng: 584.616 instance trong mẫu 19-file.

### 5.1 Các trường của đối tượng channel

```jsonc
{
  "type": "Val",                 // value kind - see § 5.2
  "when": [0, 12, 24],           // keyframe frame numbers (ints), ascending
  "val":  [0.0, 1.0, 0.5],       // one value per keyframe
  "interp": [ {...}, {...}, {...} ],   // one entry per keyframe - see § 5.3
  "mute": false,                 // channel disabled?
  "ref":  false,                 // meaning not decoded
  "actions": [ { "name": "EyeBlink", "pose": {...} } ],   // optional - see § 11
  "split":  [ {...}, {...} ]     // optional, Vec2/Vec3 only - see § 5.4
}
```

- `when`, `val` và `interp` **luôn có đúng cùng độ dài** — đã kiểm chứng trên
  toàn bộ 584.616 channel (tổng 19-file), không ngoại lệ nào. `interp[i]` mô
  tả segment rời khỏi keyframe `i`.
- `mute` là `false` trên tất cả trừ **một** channel trong mẫu 19-file:
  `transforms.translation` của chính root `BoneLayer` của `Bandit.mohoproj`
  là `mute: true` **(đính chính — điều này nằm trong mẫu 5-file ban đầu; một
  bản sửa cũ của tài liệu này báo `mute` là false ở mọi nơi)**. Channel đó có
  một keyframe duy nhất tại `{0,0,0}` mặc định, nên mute nó không có hiệu ứng
  thấy được theo chiều nào cả — khoảng trống vẫn chưa được kiểm thử cho một
  tài liệu nơi một channel *nhiều keyframe* bị mute. `ref` là `true` trên 207
  channel trong 3 tài liệu (đa số là các channel `transforms.translation`
  một-keyframe trong rig import PSD của `BoneStrengthTool.animeproj` và
  `OffsetBoneTool.animeproj`, cộng một channel `timeline_markers` trong
  `Bandit.mohoproj`) **(phát hiện từ 19 file, cũng đính chính phát biểu
  "false ở mọi nơi" trước đó)** — ý nghĩa của nó vẫn chưa giải mã, và mọi
  trường hợp được mẫu tình cờ là một keyframe đơn, không xung đột, nên chưa
  có gì về đầu ra hiện tại được biết là sai. `moho2svg.py` không đọc trường
  nào trong hai trường đó. **Một channel `mute: true` có nhiều hơn một
  keyframe sẽ bị công cụ này hoạt ảnh một cách âm thầm trong khi Moho đóng
  băng nó** — một khoảng trống chưa kiểm thử, không phải lỗi đã xác nhận, vì
  không mẫu nào khai thác tổ hợp đó.
- Một trường không bao giờ hoạt ảnh đôi khi được lưu như một scalar trần hoặc
  một dict thường thay vì một đối tượng channel. Cả hai dạng đều được chấp
  nhận một cách trong suốt (`Channel` coi một scalar trần như một keyframe
  đơn).

`moho2svg.py` đánh giá một channel bằng một **cubic đơn điệu giữa hai keyframe
bao quanh**, kẹp ở cả hai đầu, bỏ qua hoàn toàn `interp`. Điều đó chính xác
tại các keyframe và xấp xỉ giữa chúng. Hình dạng đường cong được suy ra bằng
cách chấm điểm đầu ra render so với các frame của chính Moho, không phải được
giải mã từ file — xem
[`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 3.6.

### 5.2 Các loại channel và hình dạng phần tử `val`

`type` đặt tên cho loại giá trị. Hình dạng phần tử của mảng `val` theo sau
nó, nhất quán, không ngoại lệ nào quan sát thấy:

| `type` | Phần tử `val[]` | Số đếm | Các trường ví dụ |
|---|---|---|---|
| `Val` | float | 143.724 | `width`, `smoothness`, `weight_in`/`weight_out`, `offset_in`/`offset_out`, `color_strength`, `anim_angle`, `anim_scale`, `rotation_z`, `blur` |
| `Color` | `{r, g, b, a}`, float `0.0–1.0` | 22.969 | `fill_color`, `line_color`, điểm `color` |
| `Vec2` | `{x, y}` | 22.311 | mesh point `position`, `anim_pos`, `effect_offset`, `ik_parent_target` |
| `Bool` | bool | 9.341 | `flip_h`, `flip_v`, `layer_effects.visibility`, `ik_lock`, `bone_dynamics` |
| `Vec3` | `{x, y, z}` | 1.757 | `transforms.translation`, `transforms.scale`, `transforms.shear` |
| `String` | str | 1.083 | `switch_keys`, `shape_order`, `layer_ordering`, `timeline_markers` |

Chú ý rằng `transforms.translation` và `transforms.scale` là **`Vec3`, không
phải `Vec2`** — thành phần `z` hiện diện và công cụ này bỏ qua nó (một
exporter 2D, nên điều này cố ý, nhưng nó đúng nghĩa là độ sâu layer bị bỏ
rơi).

### 5.3 Các mục `interp`

Mỗi `interp[i]` là một đối tượng hình dạng cố định. Công cụ này bỏ qua toàn
bộ nó; nó được tài liệu hóa ở đây vì nó chính là thứ làm cho việc nội suy
giữa các keyframe không chính xác.

| Trường | Các giá trị quan sát thấy | Ghi chú |
|---|---|---|
| `t` | `0` (208.858), `4` (757), `2` (540), `6` (3), `1` (2) | Loại nội suy. **Ánh xạ enum chưa giải mã.** `0` là mặc định áp đảo. Các giá trị không phải `0` xuất hiện gần như chỉ trên `pose`, `anim_pos`, `anim_angle`, `anim_scale`, và `physics_motor_speed`. |
| `v1`, `v2` | `(0.1, 0.5)` trên 208.079 mục; cũng có `(-1, -1)`, `(-1, 2)`, `(15, -1000000)` | Hai tham số phụ thuộc loại. `(0.1, 0.5)` trông như một mặc định không dùng mang trên các keyframe thường. |
| `im` | `1`, `3`, `5`, `9`, `0` | Chưa giải mã. Có thể là một bit field. |
| `in` | `1`, `0` | Chưa giải mã. |
| `s` | `false` ở mọi nơi | Chưa giải mã. |
| `h` | `0` ở mọi nơi | Chưa giải mã. |
| `b` | vắng trên tất cả trừ 16 mục | Khi hiện diện: một danh sách các `{ao, ai, po, pi}` — có lẽ là các tay nắm Bezier tường minh cho đường cong thời gian (angle/position, out/in). Chỉ từng thấy cùng `t == 4`, nhưng đa số mục `t == 4` không có `b`, nên `t == 4` không đơn giản là "Bezier". |

Một lượt sau cũng đi xuống các channel `actions[].pose` và `split[]` đếm
604.139 mục `interp` thay vì ~210.000 đằng sau bảng trên (các số đếm `t`
khác không khớp chính xác; tổng `t == 0` thì không), và giải mã một phần
bảng: `b` hiện diện trên 182 mục, luôn đúng những mục có `im == 9`, và độ dài
của nó bằng số thành phần của giá trị channel (1 cho `Val`, 2 cho `Vec2`, 3
cho `Vec3`). Xem [`moho-animation-and-transform.md`](moho-animation-and-transform.md)
§ 3 để biết phân tích đó, kể cả marker vòng lặp mang trong `im`/`v1`/`v2`.

### 5.4 `split` — keyframes theo trục

Một channel `Vec2` hoặc `Vec3` có thể mang một danh sách `split` giữ **một
channel `Val` độc lập trên mỗi trục**, với `when`/`val`/`interp` riêng. Đây
là tính năng "tách đường cong x và y" của Moho.

Quan sát thấy đúng một lần, trên một `Vec2` `anim_pos` trong tài liệu `1045`,
nơi keyframes của channel X bị tách khớp keyframes của cha. `moho2svg.py`
không đọc `split`; nó đọc các mảng `Vec2`/`Vec3` của cha. **Nếu một tài liệu
từng tách một channel rồi keyframe các trục khác nhau, công cụ này sẽ dùng
các giá trị cha cũ** — một khoảng trống chưa kiểm thử.

### 5.5 `animated_values` cấp tài liệu

`doc.animated_values` là một đối tượng gồm năm channel, tất cả đúng một
keyframe tại frame `0` trong cả 19 tài liệu:

| Khóa | `type` | Giá trị thấy | Ý nghĩa |
|---|---|---|---|
| `camera_track` | `Vec3` | `{0, 0, 3.732051}` trong 18 của 19; `{0.232877, 0.481034, 3.732051}` trong `Rabbit.animeproj` **(phát hiện từ 19 file — một pan camera x/y thật, không phải mặc định)** | Vị trí camera. Giá trị `z` là khoảng cách camera mặc định. |
| `camera_pan_tilt` | `Vec2` | `{0, 0}` trong mọi tài liệu | Pan/tilt camera. |
| `camera_zoom` | `Val` | `2.0` trong 18 của 19; `1.413848` trong `Rabbit.animeproj` | Zoom camera. **Đính chính:** một bản sửa cũ của tài liệu này báo `0.0` từ mẫu 5-file; kiểm tra trực tiếp cho thấy giá trị thật là `2.0` trong mọi file của cả 5 file ban đầu, không phải `0.0`. Liệu `2.0` có phải giá trị zoom trung tính/no-op của Moho, hay một zoom không-mặc định thật mà công cụ này đáng lẽ áp dụng, chưa được giải mã. |
| `camera_roll` | `Val` | `0.0` trong mọi tài liệu | Roll camera. |
| `timeline_markers` | `String` | `""` trong mọi tài liệu | Chú thích timeline của editor. |

Không cái nào trong số này được `moho2svg.py` đọc (đã xác nhận: không có tham
chiếu nào tới `animated_values` hay bất kỳ khóa `camera_*` nào trong mã
nguồn). Công cụ này render với một camera cố định ngầm. **Một tài liệu có
camera bị dịch hoặc zoom sẽ xuất với khung hình sai.** Với giá trị `camera_zoom`
đã đính chính ở trên và pan thật của `Rabbit.animeproj`, điều này **kém chắc
chắn hơn phát biểu trước đây** — chưa xác nhận rằng "mọi mẫu nằm tại mặc
định", chỉ xác nhận `camera_pan_tilt`/`camera_roll` nằm như vậy, và giá trị
khác không đồng đều của `camera_zoom` trên cả 19 file có thể chính nó là mặc
định trung tính thay vì một zoom thật. Cho đến khi điều đó được giải quyết,
hãy coi đây là một rủi ro mở, không phải rủi ro vô hình.

---

## 6. Layers

### 6.1 Các loại layer

Mỗi layer là một đối tượng JSON với một trường `type` đặt tên cho loại của
nó:

Các số đếm dưới đây là khắp 19 tài liệu được mẫu.

| `type` | Số đếm | Ý nghĩa | Được render? |
|---|---|---|---|
| `MeshLayer` | 648 | Vector artwork (points/curves/shapes) — loại layer duy nhất thực sự vẽ pixel. | **có** |
| `GroupLayer` | 103 | Các con không có skeleton. | **có** (container) |
| `BoneLayer` | 47 | Một skeleton (`skeleton.bones`) cộng các layer con bị nó biến dạng. | **có** (container + skinning) |
| `TextLayer` | 34 | Một chú thích. Moho giữ các đường viền glyph đã dàn trang trong một trường `mesh_layer` lồng nhau, là một đối tượng `MeshLayer` **đầy đủ** — không phải một cặp `{type, mesh}` tối giản, nó mang toàn bộ tập trường `MeshLayer` (các trường noise/sketchy, `3d_mode`, `3d_options`, các đường dẫn/fileref texture) **(xác nhận tập-trường-đầy-đủ là phát hiện từ 19 file)**. | **có**, qua `mesh_layer` |
| `SwitchLayer` | 17 | Các con là các phương án thay thế; chỉ một cái hiển thị tại một thời điểm. | **có** |
| `ImageLayer` | 15 | **(Phát hiện từ 19 file, không có trong mẫu 5-file ban đầu.)** Một layer ảnh raster/phim/import PSD — xem [§ 6.5](#65-imagelayer-phát-hiện-từ-19-file). | **không** — bị bỏ âm thầm |
| `PatchLayer` | 12 | Không có mesh riêng — tái dùng mesh của một layer khác ([§ 12](#12-patch-layers)). | **có**, được phân giải |
| bất cứ thứ gì khác | 0 trong 19 file này | Audio, particle, note, 3D layers v.v. không được mô hình hóa. | không |

### 6.2 Các trường chung ảnh hưởng render và **được dùng**

Hiện diện trên mọi loại layer trừ khi có ghi chú.

- `name` — tên layer. Được dùng bởi `--layer` và `--mask-container`.
- `visible` (bool) — các layer ẩn bị bỏ qua trừ khi `--include-hidden`.
- `edit_only` (bool) — giữ cho tiện chỉnh sửa, không bao giờ render.
- `layers` — các layer con, chỉ trên các loại container. Một layer có thể
  không có mesh **và** không có khóa `layers` nào cả; Moho không vẽ gì cho
  nó, thậm chí không phải một group rỗng. Một `PatchLayer` đúng là trường
  hợp này *trước khi* target của nó được phân giải.
- `transforms` — transform cục bộ riêng của layer. Mười channel, trong đó
  năm cái được dùng: `translation` (`Vec3`), `scale` (`Vec3`), `rotation_z`
  (`Val`), `flip_h`, `flip_v` (`Bool`). Rotation và scale xoay quanh `origin`,
  không phải quanh `(0, 0)` cục bộ.
- `origin` — `{"x":.., "y":..}`, thường (không phải channel), trục xoay cho
  transform trên.
- `parent_bone` — chỉ số vào `skeleton.bones` của một `BoneLayer` tổ tiên,
  hoặc `-1`. `-1` nghĩa là binding *mềm* ("region"); một chỉ số không âm
  nghĩa là binding *cứng* vào đúng một bone đó. Xem [§ 9](#9-bones-và-skinning).
  Quan sát thấy trong mẫu 19-file: `-1` trên 813 của 876 layers, 54 layers
  gắn cứng vào một chỉ số không âm, và **`-3` trên 9 layers — tất cả là các
  `ImageLayer` cũng mang một `flexi_bone_subset` không tầm thường (phát hiện
  từ 19 file, chưa giải mã — xem [§ 6.5](#65-imagelayer-phát-hiện-từ-19-file))**.
  `moho2svg.py` chỉ phân biệt `-1` với `>= 0`, nên `-3` hiện được xử lý như
  mọi giá trị âm khác (tức là như binding mềm), điều chưa được xác nhận so
  với đầu ra Moho thật cho giá trị này.
- `flexi_bone_subset` — một danh sách **các chỉ số bone dưới dạng chuỗi** tách
  bởi `"|"`, ví dụ `""` (mọi bone), `"0"`, `"1|2"`, `"30|31|32|33|34|35"`.
  Giới hạn binding mềm vào những bone đó. Đây là các chỉ số vào
  `skeleton.bones`, *không phải* tên, và không liên quan tới `mesh.groups`
  ([§ 7.10](#710-nhóm-điểm-meshgroups)).
- `masking` / `group_mask` — xem [§ 10](#10-masking).
- `actions` — một registry tên action; xem [§ 11](#11-actions-và-smart-bones).
- `uuid` — nhận dạng layer, được tham chiếu bởi `PatchLayer.target_layer_uuid`
  và bởi các trường `*_layer_uuid` khác nhau bên dưới.

### 6.3 Các trường chung ảnh hưởng render và **không** được dùng

Đây là danh sách khoảng trống quan trọng: mọi trường ở đây thay đổi những gì
Moho vẽ.

| Trường | Hình dạng | Các giá trị quan sát thấy | Hệ quả của việc bỏ qua nó |
|---|---|---|---|
| `layer_effects.alpha` | channel `Val` | `1.0` trên 535 layers, **`0.6` trên 9 layers** | Opacity layer. **Cái này thực sự được các mẫu khai thác** — chín layer đáng lẽ render ở 60% mà lại render hoàn toàn đặc. |
| `blend_mode` | int | `0` trên 528 layers, **`1` trên 16 layers** | Blend mode layer. `0` chắc là Normal; `1` chưa giải mã. 16 layers hòa trộn khác trong Moho so với trong SVG. |
| `layer_effects.visibility` | channel `Bool` | `true` ở mọi nơi | show/hide **hoạt ảnh**, độc lập với cờ tĩnh `visible`. Sẽ cho phép một layer xuất hiện giữa hoạt ảnh. |
| `layer_effects.blur`, `.noise`, `.pixelation`, `.threshold`, `.ambient_occlusion` | các channel `Val` | `0.0` ở mọi nơi | Các effect ảnh theo layer. Tất cả tắt trong các mẫu. |
| `layer_outline` | `{on, color, width}` | `on: false` ở mọi nơi | Một đường viền thêm viền quanh toàn bộ layer. |
| `layer_shadow` | `{on, angle, blur, color, expansion, offset, threshold, noise_amp, noise_scale, clip_to_group}` | `on: false` ở mọi nơi | Drop shadow. |
| `layer_shading` | `{on, angle, blur, color, contraction, offset, threshold, noise_amp, noise_scale}` | `on: false` ở mọi nơi | Shading trong. |
| `perspective_shadow` | `{on, blur, color, scale, shear, threshold}` | `on: false` ở mọi nơi | Shadow phối cảnh. |
| `layer_color` | `{on, color}` | `on: false` ở mọi nơi | Một override màu phẳng cho toàn bộ layer. |
| `transforms.rotation_x`, `.rotation_y` | các channel `Val` | `0.0` ở mọi nơi | Rotation 3D. Một exporter 2D không thể biểu diễn các giá trị này. |
| `transforms.shear` | channel `Vec3` | `0` ở mọi nơi | Shear. Có thể biểu diễn trong một ma trận SVG, nhưng không làm. |
| `transforms.translation.z`, `.scale.z` | float | các mặc định | Độ sâu layer. |
| `transforms.following`, `.physics_nudge` | các channel | các mặc định | Offset theo-dường-và dịch chuyển physics. |
| `motion_blur` | `{on, frames, radius, skip, alpha_start, alpha_end, frame_percentage, extended_frames, sub_frames}` | `on: false` | Motion blur. Dù sao cũng vô nghĩa cho một xuất một-frame. |
| `distortion_layer_uuid` | str | `""` trong tất cả 827 layers có nó; **vắng mặt trong file `1021`** | Trỏ tới một layer khác được dùng như mesh biến dạng — móc lưu trữ khả dĩ nhất cho Smart Warp. Xem [`moho-rigging-and-deformation.md` § 5](moho-rigging-and-deformation.md#5-smart-warp). |
| `follow_layer_uuid`, `follow_curve`, `follow_bending`, `rotate_to_follow` | str/int/bool | `""`, `-1`, các mặc định | Rigging "follow path". |
| `physics`, `gravity`, `wind`, `enable_physics`, `use_baked_physics` | objs/channels | bị vô hiệu | Mô phỏng physics 2D. |
| `scale_compensation`, `scale_normalization` | bool/float | các mặc định | Stroke width của một layer phản ứng với scaling thế nào. Liên quan tới [§ 7.6](#76-bề-rộng-stroke) nếu từng khác mặc định. |
| `layer_ordering` | channel `String` | `""` | Sắp xếp lại con theo hoạt ảnh (với `animated_layer_order` trên `BoneLayer`). Sẽ thay đổi thứ tự vẽ theo frame. |
| `timing_offset` | int | `0` ở mọi nơi | Dịch toàn bộ timeline của layer này. Khác không sẽ làm lệch frame công cụ này đánh giá. |
| `layer_ref_*` (`uuid`, `path`, `fileref`, `mod_date`, `same_doc`) | mixed | rỗng | Layer ngoài được liên kết/tham chiếu. Một tài liệu dùng chúng sẽ thiếu artwork ở đây. |
| `camera_immune`, `dof_immune`, `face_camera`, `face_camera_mode`, `3d_mode` | mixed | các mặc định, `face_camera_mode: 2` | Hành vi 3D / camera. |
| `3d_options` (`Mesh3DOptions`) | obj | xem [§ 6.4](#64-các-trường-riêng-theo-loại) — hiện diện trên mọi `MeshLayer` (648 instance), luôn tại các mặc định giống hệt | Các cài đặt render 3D-extrusion, hoàn toàn trơ trong mọi mẫu vì `3d_mode` là `0` ở mọi nơi. |
| `quality_flags` | int | `4092`, `4094`, `45052`, `45054`, `2044` | Một bit field các công tắc render theo layer. Chưa giải mã. |
| `label_col`, `expanded`, `shown_in_timeline`, `selected`, `random_num`, `layer_user_tags`, `layer_user_comments`, `ignored_by_layer_picker`, `consolidated_channels`, `render_only`, `mask_expansion`, `modification_date` | mixed | — | Trạng thái editor, hoặc (với `render_only` / `mask_expansion`) các công tắc render chưa giải mã tắt trong mọi mẫu. |
| `metadata`, `script_data` | obj | xem [§ 6.4](#64-các-trường-riêng-theo-loại) | Các túi ghi chú editor/script, tập khóa nay đã được liệt kê. |

### 6.4 Các trường riêng theo loại

**`MeshLayer`** — `mesh` là trường duy nhất được dùng ([§ 7](#7-mô-hình-mesh)). Không dùng:

- `fill_texture_path` / `fill_texture_fileref`, `line_texture_path` /
  `line_texture_fileref` — các texture ảnh cho fills và lines. Rỗng trong mọi
  mesh layer.
- `noisy_lines`, `noisy_shapes`, `extra_sketchy`, `extra_lines`, `noise_amp`,
  `noise_scale`, `noise_interval`, `animated_noise` — vẻ ngoài "sketchy
  lines". `extra_sketchy: true` với `extra_lines: 5` trên **2 layers** (trong
  `SketchBone`), nên hai layer đó đáng lẽ render với các stroke nhấp nhô lặp
  lại mà không làm.
- `gap_filling`, `exclude_lines_from_mask`, `antialiasing`.
- `triangulated`, `squashable_deformer`, `frame_zero_deformer` — ba cờ
  deformer tồn tại **chỉ trong thế hệ định dạng `1045`** (toàn bộ 21
  `MeshLayer` của `Bandit.mohoproj`; vắng trên mọi layer `1038` và `1021`),
  tại `false`/`false`/`true` khắp nơi. Chúng là dấu hiệu rõ nhất trong mẫu
  này rằng một mesh có thể hoạt động như một mesh biến dạng — xem
  [`moho-rigging-and-deformation.md` § 5.2](moho-rigging-and-deformation.md#52-các-file-thực-sự-cho-thấy-gì).
- `3d_mode` (luôn `0`) và `3d_options` — xem `Mesh3DOptions` bên dưới.
- `metadata` — xem bên dưới.

**`Mesh3DOptions`** (`MeshLayer.3d_options`) — **(phát hiện từ 19 file.)** Mười
cài đặt 3D-extrusion bị khóa bởi `3d_mode`, hiện diện trên **từng `MeshLayer`
được mẫu** (648 instance, kể cả cái lồng bên trong mỗi `TextLayer`), luôn tại
các giá trị mặc định giống hệt:
`3d_shading_mode: 1`, `3d_shading_density: 50`,
`3d_shading_color: {64,64,64,255}` (RGBA 0–255 thường), `3d_silhouette_edges`
/ `3d_material_edges` / `3d_crease_edges: true`,
`3d_crease_angle: 1.047198` (π/3), `3d_edge_extension: 0.0`,
`3d_backface_removal` / `3d_reset_z: false`. Vì `3d_mode` là `0` trong mọi
mẫu, toàn bộ khối hiện trơ — nhưng nó lớn và hoàn toàn không được tài liệu
hóa trước lượt này; một tài liệu thực sự bật 3D extrusion sẽ xuất thành hình
học 2D phẳng không extrusion và không 3D shading chút nào. Danh sách trường
đầy đủ trong `Mesh3DOptions` của `schema/layer.schema.json`.

**`BoneLayer`** — `skeleton` và `actions` được dùng. `skeleton` là
`{type, binding_mode, bones}`, cộng `bones_groups` trong tài liệu `1045`
(hiện diện nhưng rỗng ở đó). `binding_mode` là `1` trên 41 của 42 skeleton
thực sự giữ bones, và **`2` trên một** (`OffsetBoneTool.animeproj`, layer
`Happy Dance`) — một bản sửa cũ của tài liệu này khẳng định `1` ở mọi nơi,
quá mạnh. Ý nghĩa của nó chưa giải mã, và công cụ này không bao giờ rẽ nhánh
trên nó. Cũng mang `grandpa_bone` (cho phép bones gắn các layer lồng sâu hơn
các con trực tiếp), `flexi_bone_elbow`, `animated_layer_effects` — không cái
nào được dùng. Xem `layer_ordering`/`animated_layer_order` và
`gravity`/`wind` bên dưới, cả hai dùng chung với `GroupLayer` nhưng có hình
dạng khác.

**`GroupLayer`** — không có trường render thêm nào ngoài tập chung, nhưng xem
`gravity` bên dưới.

**`layer_ordering` / `animated_layer_order` của container (`BoneLayer` và
`GroupLayer`) — (phát hiện từ 19 file).** `layer_ordering` là một channel
`String` nhằm hoạt ảnh hóa thứ tự vẽ con theo thời gian;
`animated_layer_order` là bool khóa xem nó có hoạt động hay không. Hiện diện
trên ~150 container trong mẫu (gần như mọi `BoneLayer`/`GroupLayer`) — nhưng
giá trị của `layer_ordering` là một **chuỗi rỗng trong từng instance**, và
`animated_layer_order` là `true` chỉ trên 2 container trong toàn bộ mẫu
(`ControlBones.animeproj`, `SketchBone.animeproj`), nơi channel đi kèm vẫn
rỗng. Nên không tài liệu nào được mẫu thực sự sắp xếp lại các con của nó theo
thời gian, và `moho2svg.py` — thứ luôn dùng thứ tự mảng `layers` thô — là
đúng cho mọi file ở đây, nhưng sẽ xếp layers sai cho một tài liệu thực sự dùng
tính năng này.

**`gravity` / `wind` (physics bone và group) — (phát hiện từ 19 file.)** Hai
trường không liên quan dùng chung tên `gravity` với **hình dạng khác nhau**:
`BoneLayer.gravity` là `{direction, strength}` dưới dạng **các channel `Val`**
(radian / độ lớn — quan sát thấy `direction: 4.712389` = 3π/2, tức hướng
thẳng xuống); `GroupLayer.gravity` là `{x, y}` dưới dạng **các float thường**.
`BoneLayer` cũng có một trường `wind` (`{direction, strength,
turbulence_amplitude, turbulence_frequency}`, cũng là channels).

**Cả hai trường chỉ tồn tại từ format 1045**, và đó là lý do trước đây chúng
trông có vẻ hiếm: lúc đếm lần đầu, `Bandit.mohoproj` là tài liệu 1045 duy
nhất. Một bản lưu lại ở 1045 của `SketchBone.animeproj` từ Moho Pro 14.4 —
tài liệu không hề dùng physics — mang `wind.strength = 100.0` trên **cả năm**
`BoneLayer` của nó và `gravity = {x: 0, y: -10}` trên mọi `GroupLayer`. Vậy
đây là giá trị mặc định theo từng layer mà Moho luôn ghi ra, không phải dấu
hiệu có gì đang được mô phỏng. Cờ `wind_dynamics` trên từng bone nhiều khả
năng mới là công tắc đăng ký (false trên mọi bone của cả hai tài liệu 1045),
nhưng điều đó **chưa được giải mã**. Không trường nào được `moho2svg.py` đọc.

**`SwitchLayer`** — `switch_keys` (một channel `String` có các mục `val` là
**tên các layer con**) chọn con đang hoạt động; được dùng. Không dùng:
`switch_interpolation`, `switch_data` (`""` trong mọi mẫu),
`frame_by_frame`, `previewAlignment`. Một `SwitchLayer` cũng mang một đối
tượng `skeleton` riêng (với danh sách `bones` rỗng trong mọi mẫu) — đừng
nhầm nó với một `BoneLayer`.

**`PatchLayer`** — `target_layer_uuid` và `target_layer_id`; xem
[§ 12](#12-patch-layers).

**`TextLayer`** — `mesh_layer` lồng nhau là thứ được render, nên metadata text
chỉ mang tính thông tin: `text` (chuỗi ký tự thật, `\n` cho xuống dòng),
`font` (ví dụ `"Tamales Regular Normal Upright"`), `textsize`,
`justification` (`0`, `1`), `leading`, `kerning`, `fill`, `stroke`,
`fillcolor` / `linecolor` (RGBA `0–255` thường, không phải channels),
`linewidth`, `textinheritedstyle1` / `textinheritedstyle2`, và mười một trường
`balloon*` cho bong bóng hội thoại (tất cả tắt trong các mẫu). Vì các đường
viền glyph đã được bake sẵn vào `mesh_layer`, bỏ qua các trường font không mất
gì — **trừ khi** một viewer cần dàn lại text, điều công cụ này không bao giờ
làm. `TextLayer` là loại layer duy nhất không bao giờ mang một danh sách
`actions`. **`mesh_layer` được xác nhận là một đối tượng `MeshLayer` đầy đủ,
không phải một cặp `{type, mesh}` tối giản (phát hiện từ 19 file)** — nó
mang toàn bộ tập trường `MeshLayer`, kể cả `Mesh3DOptions`, các đường dẫn
/fileref texture, và các trường "sketchy lines", tất cả cũng không được dùng.

**Các túi `metadata` / `script_data` theo layer — (phát hiện từ 19 file.)**
Cả hai là các túi khóa/giá trị tự do nhỏ, tách biệt với `metadata` cấp tài
liệu trong [§ 2](#2-cấu-trúc-cấp-cao-nhất). `metadata` xuất hiện trên các
instance `MeshLayer`, `BoneLayer`, và `SwitchLayer`; các khóa quan sát thấy:
`what` (`0`), `NewLayerScript` (bool), `LM_GrandpaBones` (bool, chỉ
`SwitchLayer`, có lẽ là cùng tính năng như `BoneLayer.grandpa_bone`),
`psd_layers` (một danh sách các chỉ số layer PSD nối bằng `"|"`, ví dụ
`"24|12|7|23|..."`, trên `BoneLayer` bọc một import cutout-puppet PSD — ghi
lại các layer PSD nào trở thành các con `ImageLayer`), và một họ công tắc
boolean `g_<number>` (`g_10000`, `g_10001`, `g_10002`, `g_10031`, `g_10033`,
`g_10056`, `g_10069`, `g_10082` quan sát thấy). `script_data` (hiếm — 2
instance `BoneLayer` trong `WhatIsBone.animeproj`) có hình dạng
`{NewLayerScript, what}`. Không túi nào được `moho2svg.py` đọc.

### 6.5 `ImageLayer` (phát hiện từ 19 file)

Một layer ảnh raster/phim/import PSD, vắng trong mẫu 5-file ban đầu — được
tìm thấy trong rig cutout-puppet "dude side.psd" của `BoneStrengthTool.animeproj`
(một `ImageLayer` cho mỗi layer PSD, 15 tổng cộng, mỗi cái gắn vào một tập
con bone). **Không được `moho2svg.py` xử lý gì cả, một exporter chỉ-vector —
một tài liệu dùng `ImageLayer` âm thầm mất artwork đó khi xuất.**

Nó mang cùng các trường `LayerCommon` như mọi layer khác (kể cả giá trị
`parent_bone == -3` đã ghi chú trong [§ 6.2](#62-các-trường-chung-ảnh-hưởng-render-và-được-dùng),
chỉ quan sát thấy trên các instance `ImageLayer`, luôn cùng một
`flexi_bone_subset` thật — có lẽ là một chế độ biến dạng bone-mesh-warp riêng
cho ảnh raster, chưa dịch ngược), cộng các trường riêng của nó:

| Trường | Ý nghĩa |
|---|---|
| `image_path` / `image_fileref` | File ảnh/phim nguồn. |
| `width` / `height` | Kích thước pixel thường (không phải channels). |
| `image_cropped` | Ảnh có được cắt tới một vùng con hay không. |
| `psd_layer` / `psd_layerid` | Layer PSD nào instance này đến từ. Hiện diện trên đa số, không phải tất cả, các instance được mẫu. |
| `psd_layer_bounds` | `{top, left, right, bottom}` — hộp bao của layer PSD. |
| `avi_alpha`, `movie_looping`, `interpreted_fps`, `persist_first_frame` / `_last_frame`, `premultiplied_movie`, `reverse_movie` | Các cài đặt phát lại phim nhúng. |
| `sampling_mode`, `quality_level` | Các cài đặt resampling ảnh. |
| `toon_effect`, `toon_black_threshold`, `toon_gray_threshold`, `toon_lightness`, `toon_saturation`, `toon_quantize`, `toon_min_edge_threshold`, `toon_max_edge_threshold` | Một bộ lọc hậu xử lý cel-shading trên ảnh raster. |

Không trường nào ở trên được `moho2svg.py` đọc. Xem `ImageLayer` trong
`schema/layer.schema.json` để có danh sách trường đầy đủ với mô tả theo
trường.

---

## 7. Mô hình mesh

### 7.1 Đối tượng `mesh`

`mesh` của một `MeshLayer` có ba cấu trúc song song cộng metadata:

| Trường | Ý nghĩa | Được dùng? |
|---|---|---|
| `points` | Mọi điểm được mesh dùng ([§ 7.2](#72-điểm-mesh)). | **có** |
| `curves` | Các chuỗi curve points ([§ 7.3](#73-curves-và-curve-points)). | **có** |
| `shapes` | Các vùng được tô/viền ([§ 7.4](#74-shapes-và-edges)). | **có** |
| `groups` | Các nhóm điểm có tên ([§ 7.10](#710-nhóm-điểm-meshgroups)). | không |
| `shape_order` | channel `String`; một danh sách các giá trị `shape.id` nối bằng `"\|"`, ví dụ `"23\|24\|...\|33"`. | không — xem [§ 7.9](#79-vì-sao-edges-và-shape_order-không-đáng-tin) |
| `anim_shape_order` | bool, `false` trên toàn bộ 648 mesh (tổng 19-file). Có lẽ bật keyframing `shape_order`. | không |
| `next_shape_id` | int; giá trị kế tiếp của bộ cấp phát id. | không |
| `curve_interpretation` | int: `1` trên 643 mesh, `0` trên 5 (tổng 19-file). Ý nghĩa chưa giải mã; cả hai render giống nhau ở đây. | không |

### 7.2 Điểm mesh

| Trường | Hình dạng | Quan sát thấy | Được dùng? |
|---|---|---|---|
| `position` | channel `Vec2` | hoạt ảnh trên 14 điểm | **có** |
| `width` | channel `Val` | `1.0` trên 12.797 điểm; cũng có `0.34`, `0.32`, `0.14`, `0.0`, `0.46`, `0.2`, `0.26`, … | **có** — bề rộng stroke theo điểm ([§ 7.6](#76-bề-rộng-stroke), [§ 7.7](#77-stroke-làm-thon)) |
| `curves` | list các int | các chỉ số của các curve đi qua điểm này | không (ánh xạ ngược được dựng lại từ `curves`) |
| `parent` | int | parenting cấp điểm | không |
| `colored` | bool | `false` trên toàn bộ 52.748 điểm (tổng 19-file) | không |
| `color` | channel `Color` | màu đỉnh theo điểm | không — trơ khi `colored` là `false` |
| `color_strength` | channel `Val` | `1.0` ở mọi nơi | không |
| `opacity` | channel `Val` | hiện diện trên 396 điểm (chỉ `1045`), `1.0` | không |
| `color_drift` | channel `Val` | hiện diện trên 396 điểm (chỉ `1045`) | không |
| `selected` | bool | trạng thái editor | không |

Nên tô màu theo điểm **có trong định dạng nhưng không được các mẫu này khai
thác** — `colored` là false ở mọi nơi, nên bỏ qua `color` không mất gì ở đây,
và sẽ mất nhiều trong một tài liệu dùng nó.

### 7.3 Curves và curve points

Một `curve` là một chuỗi các curve points, mỗi cái tham chiếu một mesh point
theo chỉ số. Một curve là `closed` (một segment trên mỗi điểm, điểm cuối vòng
về điểm đầu) hoặc mở (ít hơn điểm một segment).

| Trường curve | Quan sát thấy | Được dùng? |
|---|---|---|
| `points` | list các curve points (bên dưới) | **có** |
| `closed` | bool | **có** |
| `num_points` | int, khớp `len(points)` | không (thừa) |
| `start_percent` / `end_percent` | các channel `Val`; `start_percent` là `-0.1` trên toàn bộ 3.045 curves (tổng 19-file); `end_percent` là `1.1` trên tất cả trừ 3, là `1.008296` (cùng một curve "nose", dùng chung giữa 3 tài liệu hướng dẫn anh em — **phát hiện từ 19 file**, vẫn là một giá trị đơn chưa keyframe, nên không khác biệt hành vi hoạt ảnh) | không — các giá trị này cắt bớt phần được vẽ của một đường. Các mặc định kéo dài hơi quá cả hai đầu. **Một `end_percent` được keyframe là cách Moho hoạt ảnh hóa một đường tự vẽ lên chính nó, và công cụ này sẽ vẽ cả đường thay vì vậy.** |
| `profile_layer_uuid`, `profile_curve_id`, `profile_repeat`, `profile_offset` | `""`, `-1`, `16`, `0.0` | không — một "curve profile" lặp lại hình dạng của một curve khác dọc theo curve này. Chưa đặt trong mọi mẫu. |

Các trường curve point — cả bảy, tất cả được dùng:

| Trường | Hình dạng | Ý nghĩa |
|---|---|---|
| `point` | int | Chỉ số vào `mesh.points`. |
| `smoothness` | channel `Val` | Độ cong; `0` = góc sắc (các tay nắm sụp vào điểm). |
| `weight_in` / `weight_out` | các channel `Val` | Mỗi tay nắm vươn xa bao nhiêu về phía điểm lân cận của nó, như một phần của khoảng cách tới nó. |
| `offset_in` / `offset_out` | các channel `Val` | Một rotation nhỏ (radian) tạo các curve bất đối xứng. |
| `segments_on` | bool | `false` trên 583 của 53.027 curve points (tổng 19-file). `false` nghĩa là segment rời khỏi điểm này **không được vẽ** — path tách thành một subpath mới. |

**Trong thế hệ định dạng `1021`, `weight_in`/`weight_out`/`offset_in`/
`offset_out` vắng hoàn toàn** (phát hiện từ 19 file). Mỗi curve point trong
toàn bộ 305 curve point của `Rabbit.animeproj` có đúng
`{point, smoothness, segments_on}` và không gì khác, trong khi mỗi curve point
`1038`/`1045` có đủ bảy trường (12.500 curve points đã kiểm). Đây có lẽ là một
biểu diễn curve đơn giản hơn, chỉ-tay-nắm-đối-xứng, có trước tính năng
weight/offset bất đối xứng.

Trước đây đây là một **lỗi cứng khi tải**: `CurvePoint._build` đọc bốn trường
này bằng chỉ mục dict thường, nên `Rabbit.animeproj` ném
`KeyError: 'weight_in'` và không layer nào của nó xuất được cả.
`CurvePoint._build` bây giờ đọc chúng bằng `.get()` và lùi về
`CurvePoint.DEFAULT_WEIGHT` (`1.0`) và `CurvePoint.DEFAULT_OFFSET` (`0.0`).
Hai giá trị mặc định đó được chọn dựa trên hai căn cứ:

- Chúng **trung tính** trong `BezierReconstructor.handle`: weight `1.0` rút
  độ dài tay nắm về `distance * smoothness`, và offset `0.0` để hướng tay nắm
  không bị xoay. Nên một điểm `1021` hành xử đúng như curve tay-nắm-đối-xứng
  mà nó có vẻ là.
- Chúng là **giá trị phổ biến nhất trong dữ liệu** ở các tài liệu có mang các
  trường này: `1.0` trên 23,4% của 52.722 giá trị weight và `0.0` trên 26,5%
  của 52.738 giá trị offset, mỗi cái đều là giá trị hay gặp nhất với khoảng
  cách rõ rệt.

**Chưa xác nhận đối chiếu với một bản xuất Moho của tài liệu `1021`** — không
có SVG do Moho xuất làm tham chiếu cho `Rabbit.animeproj` (các SVG dưới
`out/svg/ori/` là đầu ra của chính exporter này), nên hình dạng tay nắm sinh
ra là suy luận, không phải đo đạc. Chỉ xác nhận được rằng tài liệu bây giờ
tải và xuất được mọi layer
(`python3 moho2svg.py moho/Rabbit.animeproj --list`), và rằng việc xuất lại
các tài liệu mẫu cho ra SVG giống hệt từng byte.

### 7.4 Shapes và `edges`

| Trường | Hình dạng | Quan sát thấy | Được dùng? |
|---|---|---|---|
| `edges` | `{curve: [...], segment: [...], flag: [...]}` | ba mảng int song song, luôn độ dài bằng nhau | **có** — xem [§ 7.9](#79-vì-sao-edges-và-shape_order-không-đáng-tin) |
| `has_fill` / `has_outline` | bool | `(true,true)` 408, `(true,false)` 315, `(false,true)` 236 | **có** |
| `style` | obj | style riêng của shape ([§ 8.2](#82-style-riêng-của-shape-và-sự-kế-thừa)) | **có** |
| `inherited_style_uuid` / `_name`, `inherited_style2_uuid` / `_name` | str | xem [§ 8.2](#82-style-riêng-của-shape-và-sự-kế-thừa) | **có** |
| `id` | int | nhận dạng shape, được tham chiếu bởi `mesh.shape_order` | **có** |
| `combo_mode` | int | **chỉ hiện diện trong tài liệu `1045`** (112 shapes): `0`×96, `1`×2, `3`×14 | **có** — xem [§ 7.8](#78-kết-hợp-shape-boolean) |
| `effect_scale` / `effect_rotation` | các channel `Val` | `1.0`/`0.0` trên ~895 shapes, thay đổi trên phần còn lại | **có** — nhưng chỉ để đặt một gradient |
| `effect_offset` | channel `Vec2` | đa số `{0,0}` | không |
| `fill_allowed` | bool | `true` 1.801, `false` 859 (tổng 19-file) | không — có lẽ "shape này có thể được tô chút nào", tách biệt với `has_fill` |
| `combo_blend_anim` | channel `Val` | `0.0`, chỉ `1045` | không — có lẽ hoạt ảnh hóa một blend boolean mềm |
| `3d_thickness` | channel `Val` | `0.125` trên toàn bộ 2.660 shapes (tổng 19-file) | không |
| `name` | str | `""` hoặc `"S1"`, `"S2"`, … | không |
| `selected` | bool | trạng thái editor | không |

### 7.5 Tái dựng Bezier

Một curve point không lưu các điểm điều khiển Bezier tường minh; chúng được
tái dựng từ `smoothness`, `weight_in`/`weight_out`, và `offset_in`/`offset_out`.

**Độ dài** tay nắm là `distance_to_neighbour * smoothness * weight` (đã xác
nhận chính xác so với 209 tay nắm tham chiếu). **Hướng** tay nắm *không* đơn
giản là `normalize(next - prev)` — nó là một blend có trọng số theo độ dài
dây cung của hai vector dây cung lân cận (xem phần BEZIER CURVES của module
docstring để có công thức chính xác và suy diễn kinh nghiệm của nó).

### 7.6 Bề rộng stroke

Hai đại lượng độc lập, không-phải-pixel thu nhỏ một stroke:

- `line_width` — một giá trị theo shape/style (một số ít giá trị lượng tử hóa
  trên mỗi tài liệu; 33 giá trị phân biệt trong mẫu 19-file, từ `0.001389`
  tới `0.092223` (mở rộng từ 11 giá trị của mẫu 5-file ban đầu,
  `0.002778`–`0.092223` — **phát hiện từ 19 file**). Nó là một **float thường,
  không phải channel** — Moho không hoạt ảnh hóa nó.
- điểm `width` — thường `1.0`, nhưng có thể thay đổi theo điểm.

```
stroke_px = line_width * point_width * canvas_height * layer_chain_scale
```

`layer_chain_scale` là tỷ lệ tổ tiên tích lũy, **loại trừ** biến dạng bone
(đã xác nhận: gộp nó vào làm độ phóng đại rõ tăng ~11% trên một walk cycle).

### 7.7 Stroke làm thon

Nơi các điểm của một shape không cùng chung một `width`, exporter của chính
Moho không dùng một `<path stroke-width>` biến đổi (SVG không thể biểu diễn
một cái) — nó đi dọc stroke và xuất ra đúng đường viền được tô,
thấy được như hàng chục path tô nhỏ xíu cho một thứ như cái đuôi rậm. Các
mẫu khai thác điều này nặng: 7.470 của 52.748 mesh points (tổng 19-file) có
một `width` khác `1.0`. Xem phần TAPERED STROKES của module docstring.

### 7.8 Kết hợp shape boolean

`combo_mode` nói một shape kết hợp với (các) shape ngay trước nó trong cùng
layer thế nào. Nó **vắng trong toàn bộ bốn tài liệu `1038`** và hiện diện trên
toàn bộ 112 shapes của tài liệu `1045` — hãy coi `combo_mode` vắng mặt là `0`.

| `combo_mode` | Số đếm ở đây | Ý nghĩa |
|---|---|---|
| `0` | 96 | Bình thường — bắt đầu một nhóm boolean độc lập mới. |
| `1` | 2 | Union — được trộn vào nhóm hiện tại; ranh giới dùng chung biến mất, và đường viền *kết hợp* được viền dùng styling của thành viên đầu (base) của nhóm, không phải của chính nó. |
| `3` | 14 | Intersect — bị cắt vào union của các thành viên đặc của nhóm tính đến giờ. |
| `2` | **0** | Không có trong bất kỳ tài liệu nào trong 19 tài liệu này. Module docstring báo đã thấy nó trong một file thật; không có mẫu nào ở đây để giải mã nó, và `moho2svg.py` rơi qua xử lý bình thường cho nó. |

**Đường viền riêng của một thành viên `combo_mode == 3` (intersect) không còn
hiện một khoảng trống thật mà Moho không vẽ.** `moho2svg.py` cài đặt
`combo_mode` bằng cách cắt stroke riêng của một thành viên vào fill của thành
viên base qua một `<mask>` SVG — một xấp xỉ của phép boolean, không phải một
giao điểm path hình học thật (được nói thẳng trong module docstring). Điều
này từng hỏng cho một segment curve `segments_on == false` thực sự là hình
học *duy nhất* (không, như trong trường hợp `combo_mode == 1`, là một ranh
giới dùng chung với — và đã được vẽ bởi — một thành viên nhóm khác). Đã xác
nhận trên `Eye_Upper`/`S3` của Bandit (một shape mí mắt trên `combo_mode ==
3`): một segment của curve của nó có `segments_on == false`, và các điểm đầu
cuối của segment đó không trùng với segment nào của ranh giới shape base `S1`
cả (đã kiểm trực tiếp — hai curve chiếm các tọa độ hoàn toàn khác nhau).
Moho thật nhiều khả năng tính một cạnh ranh giới mới thực sự tại điểm curve
của `S3` cắt curve của `S1`, và đánh dấu segment `S3` gốc đó
`segments_on == false` vì một cạnh được tính đã *thay thế* nó.

Thay vì tái dựng cạnh đó (giao điểm Bezier–Bezier thật — một lớp thuật toán
khác với bất cứ thứ gì khác trong công cụ này), bản sửa né việc cần nó: riêng
cho một thành viên `combo_mode == 3`, `_render_shape` giờ dựng stroke với
`visible_only=False` — tức là nó vẽ đường viền đóng gốc đầy đủ của thành viên
thay vì bỏ segment ẩn. Clip intersect hiện có (`_mask_union`, không đổi) sau
đó cắt đường viền đầy đủ đó xuống trong fill của shape base đúng như trước —
và vì clipping của chính SVG tính điểm cắt hình học thật khi mask được
raster hóa, kết quả thấy được ra đúng mà công cụ này không bao giờ tự tính
một giao điểm Bezier. Đã xác nhận: `S3_line` của `Eye_Upper` giờ là một
subpath liên tục (trước là hai, bị tách bởi một `M`), và khoảng trống đã biến
mất. Điều này chỉ đụng các shapes VỪA là `combo_mode == 3` VỪA có một segment
`segments_on == false` — đã kiểm khắp cả năm tài liệu tham chiếu,
`Eye_Upper`/`S3` là cái **duy nhất**, nên không gì khác có thể hồi quy. Liệu
một thành viên intersect có bao giờ hợp pháp muốn khoảng trống-do-nghệ-sĩ-vẽ
của chính nó (thứ bản sửa này giờ sẽ khôi phục sai) vẫn chưa xác nhận —
chưa tìm thấy ví dụ nào như vậy, nhưng chỉ có đúng một tham chiếu
`combo_mode == 3`-có-khoảng-trống tồn tại tổng cộng. Xem phần BOOLEAN SHAPE
COMBINATIONS của module docstring.

### 7.9 Vì sao `edges` và `shape_order` không đáng tin

Danh sách `edges` của một shape không đáng tin là một bước đi theo thứ tự
danh sách, và `flag` của nó không đáng tin là một bit hướng (quan sát thấy:
`flag` `0` trên 15.477 edges, `1` trên 872, với các file thật nơi thứ tự
segment giảm nghiêm ngặt và `flag` là `0` khắp nơi, và nơi các segment của
một curve được liệt kê ngoài thứ tự bước đi). `edges` phải được coi là một
*tập không thứ tự* các segment và được truy lại như một đồ thị vô hướng, đúng
như `PathTracer` làm.

`mesh.shape_order` cũng gây hiểu lầm tương tự: nó là một registry tăng dần
các giá trị `shape.id` nối bằng `"|"`, không phải một z-order. Z-order thật
(sau ra trước) là thứ tự các shape đã xuất hiện trong `mesh.shapes`.
`moho2svg.py` không đọc `shape_order` chút nào.

### 7.10 Nhóm điểm (`mesh.groups`)

`mesh.groups` là một danh sách các `{"type": "PointGroup", "name": ...,
"points": [các chỉ số vào mesh.points]}`. 14 đối tượng point-group tồn tại
trong mẫu 19-file — cùng một tập 7 tên (`"Right Hand"` hai lần, `"Left
Laces"`, `"Right Laces"`, `"top lip"`, `"bottom lip"`, `"bottom Teeth"`), được
nhân đôi giống hệt khắp `ReparentBone.animeproj` và
`SelectandReparentBoneTool.animeproj` (hai rig hướng dẫn rất giống nhau).

Đây là một tiện ích editor để chọn điểm. **Chúng không cùng không gian tên
với `flexi_bone_subset`**, thứ giữ các chỉ số bone
([§ 6.2](#62-các-trường-chung-ảnh-hưởng-render-và-được-dùng)). Không gì trong
các mẫu tham chiếu một nhóm điểm, và công cụ này bỏ qua chúng.

---

## 8. Styles

### 8.1 Named styles (`doc.styles`)

`doc.styles` là một danh sách phẳng các đối tượng named style, được các shape
tham chiếu qua uuid hoặc tên:

```jsonc
{
  "type": "Style", "name": "yanak", "uuid": "...",
  "define_fill_color": true,  "fill_color": { ...Color channel... },
  "define_line_col":   true,  "line_color": { ...Color channel... },
  "define_line_width": true,  "line_width": 0.005556,
  "line_caps": 1,
  "brush_name": "Brush502.png", "brush_jitter": 6.283185, "brush_spacing": 0.25,
  "brush_align": false, "brush_tint": true,
  "fill_style": { "type": "SS_Gradient2", "gradient_type": 1, "gradients": [...] }
}
```

Mọi trường quan sát thấy trên một named style:

| Trường | Loại | Các giá trị quan sát thấy | Được dùng? |
|---|---|---|---|
| `type` | str | `"Style"` luôn | không |
| `name`, `uuid` | str | các khóa tra cứu | **có** |
| `define_fill_color`, `define_line_col`, `define_line_width` | bool | true/false | **có** — xem [§ 8.2](#82-style-riêng-của-shape-và-sự-kế-thừa) |
| `fill_color`, `line_color` | các channel `Color` | — | **có** |
| `line_width` | float (không phải channel) | 11 giá trị phân biệt | **có** |
| `line_caps` | int | `5.659`×`1` (round), `765`×`0` (butt) trên 6.424 đối tượng style (tổng 19-file) | **có** — `0` butt, `1` round, `2` square (ánh xạ từ `LINE_CAP_NAMES`). Mẫu 5-file ban đầu chỉ thấy `1`; **`0` là phát hiện từ 19 file** (`IndependentAngle`, `MaximumIKStrethching`, `TargetBone` mỗi cái có 255 styles với `line_caps: 0`) — đã xác nhận được khai thác trong mẫu rộng hơn, nên một style butt-cap giờ thực sự khác với những gì công cụ này vẽ nếu ánh xạ `0` của `LINE_CAP_NAMES` sai (chưa kiểm chứng với Moho cho giá trị đó). |
| `fill_style` | obj | trên 256 styles (mẫu ban đầu); 1.196 trong mẫu 19-file | **có** — gradient fill ([§ 8.4](#84-gradients)), nhưng xem [§ 8.3](#83-các-biến-thể-effect-style-phát-hiện-từ-19-file): `fill_style` không phải lúc nào cũng là một gradient. |
| `line_style` | obj | trên 25 styles (mẫu ban đầu); 116 `SS_Gradient2` + 9 `SS_Soft` + 3 `SS_Shadow` trong mẫu 19-file | **không** — xem bên dưới; không biến thể nào trong ba biến thể được đọc. |
| `fill_style_id`, `line_style_id` | int | `9` trong đa số áp đảo; cũng có `12` (`fill_style_id`, 19×), `11` và `2` (`line_style_id`, 3× và 9×) **(các giá trị không-phải-9 là phát hiện từ 19 file)** | không — củng cố rằng đây là các id tham chiếu nội bộ tùy ý, không phải một enum đóng nhỏ |
| `fill_style2`, `fill_style2_id` | obj, int | **(Phát hiện từ 19 file, vắng trong mẫu 5-file ban đầu.)** `fill_style2` giữ `SS_Texture2` trên 12 lần xuất hiện (3 file); `fill_style2_id` là hằng số `10`. Một *khe* effect fill thứ hai xếp lớp lên trên `fill_style`. | không |
| `brush_name` | str | 20+ giá trị phân biệt | **có** ([§ 8.6](#86-phân-giải-brush_name-thành-một-file)) |
| `brush_jitter` | float (radian) | `0.0`–`6.283185` | **có** |
| `brush_spacing` | float (phần của đường kính dab) | `0.0`–`0.7` | **có** |
| `brush_align` | bool | true/false | **có** |
| `brush_tint` | bool | `true` trên toàn bộ 771 | **có** |
| `brush_randomize` | bool | true/false | không |
| `brush_rand_order` | bool | true/false | không |
| `brush_merged_alpha` | bool | true/false | không |
| `brush_angle_drift` | float | `0.0`, `0.261799`, `0.349066`, `1.745329` | không |
| `brush_size_amp`, `brush_size_scale` | float | trên 12 styles (chỉ `1045`) | không |
| `brush_random_interval` | int | `1`, trên 12 styles | không |
| `brush_hue_drift`, `brush_sat_drift`, `brush_val_drift` | float | `0.0`, trên 12 styles | không |

> **Ghi chú độ chính xác.** Module docstring phát biểu rằng `brush_angle_drift`,
> `brush_randomize`, `brush_merged_alpha`, và `brush_rand_order` "được đọc từ
> style nhưng không được cài đặt". Trong code hiện tại chúng **không được đọc
> gì cả** — `ResolvedStyle.resolve` chỉ sao chép `brush_name`,
> `brush_jitter`, `brush_spacing`, `brush_align`, và `brush_tint`, và không
> tên trường brush nào khác xuất hiện trong `moho2svg.py`. Các mặc định cấp
> thư viện tương đương `randomOrder` / `randomInterval` *có* được đọc, nhưng
> từ kho `.mohobrush` ([§ 8.6](#86-phân-giải-brush_name-thành-một-file)),
> không phải từ style. Ảnh hưởng tới đầu ra là không theo cách nào cả.

### 8.2 `style` riêng của shape và sự kế thừa

Đối tượng `style` riêng của một shape có cùng tập trường như một named style.
Các tham chiếu kế thừa (`inherited_style_uuid` / `inherited_style_name` /
`inherited_style2_uuid` / `inherited_style2_name`) xuất hiện **hoặc trên chính
shape hoặc bên trong đối tượng `style` riêng của nó** — cả hai đều quan sát
thấy trong các file thật, nên cả hai đều được kiểm.

**Quy tắc phân giải.** Các giá trị `style` riêng của shape là base. Rồi, cho
mỗi named style được tham chiếu, và cho mỗi cờ `define_X` trong ba cờ **true
trên named style** và **false trên style riêng của shape**, giá trị của named
style override base. Style 1 được áp trước style 2, nên style 2 thắng khi cả
hai định nghĩa cùng một thuộc tính — đây là cách một "line style" chỉ-đường-
viền được xếp lớp lên trên một base fill style. Một gradient (`fill_style`),
`line_caps`, và các trường brush đi theo trên cùng các cờ đó.

Chú ý sự bất đối xứng: một cờ `define_X` **false trên shape** không làm trống
giá trị riêng của shape — nó chỉ làm shape *có thể bị override*. Đó là vì
sao tài liệu `1045` hoạt động được: toàn bộ 112 shapes của nó có mọi cờ
`define_*` false và không style được kế thừa, nên các giá trị riêng của chúng
được dùng nguyên văn.

Hai thế hệ dùng cơ chế này rất khác nhau:

| | Các tài liệu `1038` | Tài liệu `1045` |
|---|---|---|
| Named styles đặt `define_*` | 100% (cả 759) | **0% (0 của 12)** |
| Shapes có một tham chiếu `inherited_style*` | 557 của 847 | 0 của 112 |
| Nơi các giá trị thật sống | trong named style | trên `style` riêng của shape |
| Named styles mang `fill_style` | 256 | 0 |

Nên: **các tài liệu cũ hơn điều khiển mọi thứ qua danh sách named style; tài
liệu mới hơn hầu như không dùng nó.** Một công cụ chỉ xử lý một thế hệ sẽ âm
thầm tạo đầu ra không màu trên thế hệ kia.

### 8.3 Các biến thể effect style (phát hiện từ 19 file)

`fill_style`, `fill_style2`, và `line_style` mỗi cái giữ một *đối tượng
effect* với một `type` riêng. Mẫu 5-file ban đầu chỉ từng thấy `SS_Gradient2`,
thứ làm cho "các trường này nghĩa là một gradient" trông như một quy tắc an
toàn — không phải vậy. Mẫu 19-file cho thấy **năm** loại effect phân biệt,
và các tập biến thể fill/line rời nhau ngoại trừ `SS_Gradient2`:

| Effect `type` | Khe | Số lần xuất hiện | Các file | Các trường | Được `moho2svg.py` đọc? |
|---|---|---|---|---|---|
| `SS_Gradient2` | `fill_style` | 1.196 | 17 | `gradient_type`, `gradients[]`, `through_alpha` | **có** ([§ 8.4](#84-gradients)) |
| `SS_Gradient2` | `line_style` | 116 | 16 | như trên | không |
| `SS_Crayon` | `fill_style` | 19 | 1 | `line_width`, `density` (cả hai là channel `Val`), `clear_background`, `reduce_randomization`, `rand_seed` | không — rơi về `fill_color` phẳng của shape |
| `SS_Soft` | `line_style` | 9 | 3 | `blur_radius` (channel `Val`), `threshold` (bool thường) | không — rơi về một màu stroke phẳng |
| `SS_Shadow` | `line_style` | 3 | 3 | `angle`, `offset`, `blur` (các channel `Val`), `color` (channel `Color`), `threshold` (bool thường) | không — một drop shadow theo-shape trên stroke, tách biệt với `layer_shadow` cấp layer trong [§ 6.3](#63-các-trường-chung-ảnh-hưởng-render-và-không-được-dùng) |
| `SS_Texture2` | `fill_style2` | 12 | 3 | `path`, `SS_Texture2FileRef`, `fill_mode`, `through_alpha` | không — một fill texture ảnh xếp lớp lên trên `fill_style`; trong toàn bộ 12 lần xuất hiện được mẫu cả hai trường path rỗng, nên không tài liệu nào được mẫu thực sự phân giải một file texture |

Một shape mang `SS_Crayon`, `SS_Soft`, hoặc `SS_Shadow` vì vậy render với một
fill/stroke phẳng thường ở đây thay vì effect textured/blurred/shadowed của
Moho — một khác biệt thấy được chưa-xác-nhận-nhưng-hợp-lý mà không gì trong
mẫu 5-file ban đầu có thể làm lộ ra. `SS_Crayon` cũng được tìm thấy **trực
tiếp trên đối tượng `style` riêng của một shape** (`OffsetBoneTool.animeproj`,
shape "pant-shades"), bác bỏ một giả định trước đó của tài liệu này rằng một
fill effect được style hóa chỉ từng sống trên một named style toàn tài liệu.
Mô tả theo-trường đầy đủ: `Gradient`, `Crayon`, `SoftStyle`, `ShadowStyle`,
`Texture2` trong `schema/style.schema.json`.

### 8.4 Gradients

`fill_style` (và `line_style` không được dùng) có thể có hình dạng này — một
trong năm biến thể effect từ [§ 8.3](#83-các-biến-thể-effect-style-phát-hiện-từ-19-file):

```jsonc
{
  "type": "SS_Gradient2",
  "gradient_type": 1,          // 0 = linear (84 seen), 1 = radial (197 seen)
  "through_alpha": false,      // not used
  "gradients": [
    { "location": { ...Val channel... },   // stop position, 0.0-1.0
      "color":    { ...Color channel... } },
    ...
  ]
}
```

Cả vị trí stop lẫn màu stop đều là các channel đầy đủ, nên một gradient có
thể hoạt ảnh. `moho2svg.py` đọc `gradient_type`, `gradients[].location`, và
`gradients[].color`; nó bỏ qua `through_alpha` và bác bỏ bất kỳ `type` nào
khác `"SS_Gradient2"` với một cảnh báo.

Một shape chọn vào một gradient fill bằng cách để `define_fill_color` false
và kế thừa một style mang `fill_style`. Vị trí đặt (tâm và bán kính) được suy
ra từ hộp bao của shape, được thu nhỏ và xoay bởi `effect_scale` /
`effect_rotation` riêng của shape — **xấp xỉ, không khớp-pixel** với vị trí
đặt được tham số hóa khác của chính Moho.

### 8.5 Kiểu cọ

Đường của một named style có thể là một "brush" có họa tiết — một ảnh nhỏ
được đóng dấu lặp lại dọc theo path (nhấp nhô theo rotation, đặt cách nhau
như một phần của kích thước riêng của nó) thay vì một đường có bề rộng đồng
đều.

- `brush_name` — nhận dạng asset brush ([§ 8.6](#86-phân-giải-brush_name-thành-một-file)).
- `brush_jitter` — độ rải rotation ngẫu nhiên, tính bằng **radian**, áp theo
  từng dab.
- `brush_spacing` — khoảng cách dab, như một **phần của đường kính riêng của
  dab**.
- `brush_align` — mỗi dab có xoay theo tiếp tuyến path cục bộ (ngoài jitter
  ngẫu nhiên) hay bỏ qua hướng path hoàn toàn.
- `brush_tint` — texture (xám) có được tô lại màu thành `line_color` đã phân
  giải, hay được dùng với các pixel đa màu gốc của chính nó nguyên vẹn.
  `true` trong mọi style trong mọi mẫu.

Sự ngẫu nhiên theo-dab của chính Moho không thể khôi phục từ tài liệu đã
lưu, nên công cụ này gieo jitter của nó một cách tất định theo shape thay vì
vậy. Xem phần BRUSH STROKES của module docstring, và `moho-exporting-svg.md`
§ 7 cho ba đường render và hiệu năng của chúng.

### 8.6 Phân giải `brush_name` thành một file

Moho vận chuyển các asset brush riêng của nó như các file được cài đặt bên
cạnh ứng dụng, không nằm trong bất kỳ file dự án nào. Một asset brush có một
trong ba hình dạng trên đĩa:

1. **Một PNG đơn** tên đúng theo brush (`Brush502.png`).
2. **Một brush nhiều-frame**: một *thư mục* tên đúng theo brush (ví dụ
   `CK Ink Painty Brush/Painty Brush_00001.png` … `_00012.png`), với một file
   anh em `<name>.mohobrush`.

   Dù phần mở rộng, một file `.mohobrush` là một **kho ZIP**, không phải một
   ảnh hay một định dạng nhị phân riêng — đã xác nhận bằng cách giải nén và
   phân tích toàn bộ 101 file đi kèm một cài đặt Moho thật, không ngoại lệ. Nó
   chứa đúng một thành viên, `brush.json`, một đối tượng JSON thường với các
   tham số mặc định riêng của thư viện brush: `version`, `align`, `jitter`,
   `spacing`, `angleDrift`, `randomize`, `randomOrder`, `mergedAlpha`,
   `sizeVariationAmp`, `sizeVariationScale`, `randomInterval`, `brushFiles`
   (một danh sách các `{"brushFileRef": {"relativeTo": "Project", "path":
   "<asset name>"}}` — một con trỏ có thẩm quyền tới asset PNG/thư mục thật,
   một phương án thay thế cho việc đoán nó từ tên như phần này làm), và đôi
   khi `hueDrift`/`satDrift`/`valDrift`. Công cụ này chỉ đọc `randomOrder` và
   `randomInterval` từ nó (mỗi dab chọn một frame ngẫu nhiên đồng đều từ thư
   mục, hay duyệt qua chúng theo thứ tự tên-file-đã-sắp-xếp, tiến mỗi
   `randomInterval` dab) — xem `Exporter._brush_library_defaults`.
3. **Một ảnh preset sâu một thư mục** — các giá trị `brush_name` của một số
   tài liệu cũ chỉ phân giải tới một file sống bên trong thư mục của một brush
   khác (ví dụ `Brush549_1_50_50.png` tồn tại trên đĩa chỉ như
   `Brush004/Brush549_1_50_50.png`).

Ngoài ra, **các phiên bản Moho cũ bake thẳng tham số preset vào chính chuỗi
`brush_name`** như một hậu tố số `_N_N_...` ở cuối — file theo nghĩa đen trên
đĩa không bao gồm hậu tố. Ví dụ `Brush567_0_20_50.png` đặt tên file
`Brush567.png`; `CK Ink Natural_2_1_0_0_0_0_0_0_0` đặt tên thư mục `CK Ink
Natural`. Một số giá trị cũng mang phần mở rộng `.mohobrush` trực tiếp
(`Brush503.mohobrush`). Nên phân giải một `brush_name` nghĩa là thử, theo thứ
tự: đúng tên như một file, đúng tên như một thư mục, một tìm kiếm đệ quy cho
đúng tên file sâu một hoặc nhiều thư mục, rồi cùng ba tìm kiếm đó lần nữa sau
khi tước bỏ từng nhóm `_<chữ số>` ở cuối một lần (tái gắn phần mở rộng `.png`
đã tước nơi liên quan) cho tới khi có cái khớp.

Khắp mọi style có hậu tố thấy cho tới giờ, số **thứ hai và thứ ba** của hậu
tố khớp nhất quán với `brush_jitter` riêng của style đó (tính bằng độ) và
`brush_spacing` (dưới dạng phần trăm) — tức là chúng thừa với các trường style
đã mang tường minh, và công cụ này đọc các trường tường minh, không phải hậu
tố, cho render thực sự. Hậu tố chỉ được dùng để *định vị* file asset. Ý nghĩa
của số **thứ nhất** khác theo họ brush (nó khớp với cờ align cho họ preset
`Brush5xx`, nhưng không nhất quán cho các họ khác) và chưa giải mã.

---

## 9. Bones và skinning

> Phần này là bản ngắn. Tham chiếu trường bone đầy đủ, toán skinning, họ
> constraint/IK/control-bone/dynamics, Smart Warp, và các trường biến dạng
> cấp mesh nằm trong [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md).

`skeleton.bones` của một `BoneLayer` là một danh sách phẳng 0–157 bones.
Transform world của một bone hợp với transform của cha nó, với các cha được
phân giải bất kể thứ tự danh sách.

Các trường công cụ này dùng:

| Trường | Hình dạng | Ý nghĩa |
|---|---|---|
| `name` | str | Tên bone. Cũng là cách một dial Smart Bone được khớp ([§ 11](#11-actions-và-smart-bones)). |
| `parent` | int | Chỉ số vào cùng danh sách `bones`, hoặc `-1` cho một root. |
| `length` | float | Độ dài bone theo đơn vị tài liệu (`0.003117`–`0.981441` quan sát thấy, tổng 19-file; mẫu 5-file ban đầu thấy `0.015`–`0.6`). |
| `strength` | float | Bán kính ảnh hưởng cho binding mềm (`0.0`–`7.654676` quan sát thấy, tổng 19-file — rộng hơn đáng kể so với `0.0`–`0.6` của mẫu 5-file ban đầu; `0.0` trên một số bones nghĩa là không ảnh hưởng). |
| `anim_pos` | channel `Vec2` | Vị trí hoạt ảnh, tương đối với bone cha. |
| `anim_angle` | channel `Val` | Góc hoạt ảnh tính bằng radian. Channel được hoạt ảnh nhiều nhất trong các mẫu sau `pose` (383 của 850 bones được keyframe, tổng 19-file). |
| `anim_scale` | channel `Val` | Tỷ lệ hoạt ảnh dọc theo bone. |

Biến dạng của một mesh layer là một trong hai chế độ, được quyết định **theo
layer**:

- **Cứng (Rigid)** (`parent_bone >= 0`): mọi điểm di chuyển đúng như bone đó
  di chuyển. 54 của 842 layers (tổng 19-file).
- **Mềm / region (Flexible / region)** (`parent_bone == -1`): mỗi điểm là
  một blend có trọng số theo khoảng cách của transform của mọi bone, hoặc
  của một tập con có tên (`flexi_bone_subset`, một danh sách các chỉ số bone
  nối bằng `"|"`). **779** của 842 layers (tổng 19-file). Thêm 9 layers dùng
  `parent_bone == -3` — xem [§ 6.2](#62-các-trường-chung-ảnh-hưởng-render-và-được-dùng) —
  mà công cụ này cũng rơi qua xử lý mềm cho, chưa xác nhận với đầu ra Moho
  thật.

  **Hai quần thể layer, hai bộ số đếm.** Các con số ở đây đếm 842 layers
  trong cây `layers`. [§ 6.2](#62-các-trường-chung-ảnh-hưởng-render-và-được-dùng)
  đếm 876, vì nó cũng gộp `MeshLayer` lồng bên trong mỗi cái trong 34
  `TextLayer`; cả 34 đều là `-1`, đúng là chênh lệch 813 − 779. Cả hai bộ đếm
  đều đúng — hãy kiểm số đếm chỉ quần thể nào trước khi so sánh. Hình dạng
  suy giảm trọng số (nghịch đảo-bình phương-khoảng cách theo mặc định) là một
  heuristic, chưa được validate cho các trường hợp nơi hơn một bone có ảnh
  hưởng đáng kể gần một điểm cho trước.

Một mesh sâu vài group bên trong một `BoneLayer` bị biến dạng *trong không
gian tọa độ riêng của bone layer đó* — tức là sau các transform cục bộ của
mọi thứ giữa nó và bone layer, nhưng trước transform riêng của bone layer.

Các trường bone **không** được dùng, nhóm theo cái chúng sẽ thay đổi:

- **Reparenting theo thời gian**: `anim_parent`, một channel `Val` có các giá
  trị là các chỉ số bone (hoặc `-1`). Đây là nơi lưu trữ cho công cụ Reparent
  Bone của Moho, thứ cho phép một bone đổi cha giữa hoạt ảnh. Công cụ này
  dùng chỉ số `parent` tĩnh, nên một frame sau một keyframe reparent sẽ gắn
  bone vào sai cha.

  **Bỏ qua nó hiện miễn phí, và đo được là miễn phí.** Toàn bộ 850 channel
  `anim_parent` (tổng 19-file) có đúng **một** keyframe, và giá trị đơn đó
  bằng `parent` tĩnh riêng của bone trong **850 trên 850** trường hợp — không
  một lệch nào. Điều đó đúng ngay cả trong `ReparentBone.animeproj`, tài liệu
  trình diễn *công cụ* mà không bao giờ keyframe một reparent. Nên `anim_parent`
  hoàn toàn thừa với `parent` trong toàn bộ tập mẫu này, và rủi ro là lý
  thuyết cho tới khi một tài liệu thực sự keyframe nó xuất hiện.
- **Constraints và IK**: `constraints`, `min_constraint`, `max_constraint`,
  `fixed_angle`, `ik_lock`, `ik_global_angle`, `ik_parent_target`,
  `ignored_by_ik`, `bone_enable_arc_solver`, `target_bone`,
  `angle_control_parent` / `_scale` / `_delay`, `pos_control_parent` /
  `_scale` / `_delay`, `scale_control_parent` / `_scale` / `_delay`. Tất cả tại
  các mặc định trừ `pos_control_parent` (`4`, `5` trên một vài bone) và các
  cặp `min`/`max_constraint`. Constraints chỉ quan trọng khi pose trong
  editor; các góc kết quả đã được bake vào `anim_angle`.
- **Hành vi tỷ lệ**: `scaling_mode` (`0` trên 586 bones, `2` trên 264 — tổng
  19-file), `squash_stretch_scaling` (`0.44` hoặc `1.0`), `max_auto_scaling`.
  `scaling_mode` chưa giải mã và là một lời giải thích hợp lý cho tỷ lệ bone
  bất đối xứng được cố ý giữ lại trong `Skeleton.world_matrices`.
- **Physics/dynamics**: `bone_dynamics`, `angle_dynamics`, `pos_dynamics`,
  `scale_dynamics`, `wind_dynamics`, `spring_force`, `damping_force`,
  `torque_force`, `physics_*`, và các biến thể `pos_`/`scale_` của mỗi cái.
  **Đính chính: chúng *không phải* tất cả bị vô hiệu trong các mẫu**, như một
  bản sửa cũ của tài liệu này phát biểu. `bone_dynamics` là một channel `Bool`
  có giá trị `true` trên **115 của 850 bones**, trong 6 tài liệu —
  `WhatIsBone` (52), `Bandit` (28, tức mọi bone trong file), `AddBone` (21),
  `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2) — và
  `BoneDynamics.animeproj` keyframe nó (7 channels với hơn một key).
  `angle_dynamics` là `true` trên 2 bones trong `Bandit.mohoproj`; các biến
  thể `pos_`, `scale_` và `wind_` là `false` ở mọi nơi. Moho cộng chuyển động
  lò xo kết quả lên trên pose đã keyframe lúc phát lại, nên bỏ qua các trường
  này đánh rơi chuyển động phụ thật (follow-through, overlap) thay vì không
  gì — một khoảng trống **được khai thác**. Xem
  [`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 6.
- **Trạng thái editor**: `hidden`, `shy`, `selected`, `bone_label_showing`,
  `bone_tags`, `angle_weight`, `pos_weight`, `scale_weight`.
- **`flip_h` / `flip_v`** — các channel `Bool`, được một bản sửa cũ của tài
  liệu này xếp là trạng thái editor. **Điều đó sai**: chúng phản chiếu mọi thứ
  bone điều khiển, và giờ được áp dụng bởi `Skeleton.world_matrices` cùng cách
  các flip riêng của một layer được áp dụng (mỗi cái phủ định một cột ma trận).
  Được đặt trên đúng một bone trong mẫu 19-file — mắt cá `B23` của
  `SketchBone.animeproj`, `False` → `True` tại frame 44 — nơi bỏ qua chúng làm
  bàn chân `ayak-sol` trỏ ngược hướng trong nửa chu kỳ đi bộ. Xem
  [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md) § 3.
- **`offset`** — một `Vec2` thường, được một bản sửa cũ của tài liệu này xếp
  là trạng thái editor. **Điều đó sai**: nó khác không trên 5 bones trong
  `OffsetBoneTool.animeproj` (bằng không trên 845 cái còn lại), nơi nó gần
  như là số âm của `anim_pos` riêng của bone. Bỏ qua nó có đúng hay không phụ
  thuộc vào việc Moho dịch chỉ vị trí được vẽ của bone hay base thật của nó;
  một offset hằng số triệt tiêu khỏi `pose · rest⁻¹` theo cách nào đi nữa,
  nên trường hợp xấu nhất là các trọng số binding mềm bị dịch, không phải một
  chi bị dời chỗ. Chưa giải mã — xem
  [`moho-rigging-and-deformation.md` § 3.7](moho-rigging-and-deformation.md#37-offset-công-cụ-offset-bone).

---

## 10. Masking

Hai trường *tách biệt* tham gia:

- `group_mask` trên một *container* (`GroupLayer` hoặc `BoneLayer` — loại
  layer không quan trọng). Quan sát thấy trong mẫu 19-file: `0` (78
  containers, không masking), `2` (70 containers, masking hoạt động), và `1`
  (**đúng 2** containers). Công cụ này coi mọi giá trị khác không là "masking
  hoạt động", nên `1` và `2` hành xử giống hệt nhau ở đây; Moho có phân biệt
  chúng hay không chưa giải mã. `MeshLayer`/`TextLayer`/`PatchLayer`/
  `SwitchLayer` không mang trường này chút nào.
- `masking` trên mỗi *con* của một container masking:
  - `2` — hình học của con này định nghĩa mask (UI của Moho: kiểu "Add to
    Mask"). Nó vẫn được vẽ bình thường — là nguồn mask không ẩn nó.
  - `1` — "đừng mask layer này" — vẽ bình thường, bỏ qua mask.
  - bất cứ thứ gì khác (thường là `0`, mặc định UI của Moho) — bị cắt vào
    union của mọi anh em `masking == 2` trong cùng container.

Trong mẫu 19-file, `masking` là `0` trên 714 layers, `2` trên 93, `1` trên
62, và **`5`/`6` trên 7 layers (1× và 6× tương ứng) — (phát hiện từ 19 file,
chưa giải mã)**, rải khắp `ControlBones.animeproj`,
`OffsetBoneTool.animeproj`, và `SlickObjectTransition.mohoproj`.
`moho2svg.py` coi mọi giá trị khác `1`/`2` là "bị cắt", nên `5`/`6` hiện hành
xử như các con bị cắt thường — chưa xác nhận với đầu ra Moho thật, vì không
có xuất độc lập nào của một tài liệu dùng các giá trị này để so sánh. Chú ý
một giá trị `masking` hiện diện trên các con của các container *không* masking
nữa, nơi nó trơ.

Điều này áp dụng đồng đều ở mọi độ sâu lồng nhau, **kể cả layer cấp cao nhất
của chính tài liệu** — masking không được đối xử đặc biệt ở gốc. Một anh em
`masking == 2` không phải lúc nào cũng mang mesh riêng: một `GroupLayer` có
thể là `masking == 2` thuần túy như một container *mask*, trong trường hợp đó
silhouette hiệu dụng của nó, đệ quy, là bất cứ thứ gì chính con/con của nó
`masking == 2` định nghĩa (cùng các shape đã hoạt động như nguồn `group_mask`
nội bộ của container *đó*).

`mask_expansion` (một bool trên mọi layer, `false` khắp nơi) có lẽ phóng to
hoặc thu nhỏ cạnh mask; nó không được dùng.

**Stroke riêng của một anh em `masking == 2` vẫn thấy đầy đủ trên thứ nó
mask.** Đã xác nhận trực tiếp với ứng dụng Moho trên cặp
`Head_DarkBlue` (`masking == 0`) / `BellyTexture` (`masking == 2`) của
`Bandit.mohoproj`: stroke riêng của `BellyTexture` hiển thị không đứt đoạn ở
mọi nơi nó đè lên `Head_DarkBlue` trong Moho. Trước khi điều này được sửa,
công cụ này vẽ mọi anh em tại vị trí thứ tự-file thường của nó bất kể
`masking`, nên `Head_DarkBlue` (được liệt kê *sau* `BellyTexture`) sơn đè lên
khoảng hai phần ba trong của stroke `BellyTexture` ở bất cứ nơi nào hình học
(không mask) của chúng đè nhau — đã xác nhận bằng cách raster hóa cả hai độc
lập và diff màu pixel dọc theo đường tâm stroke của `BellyTexture` (~65% số
pixel stroke được mẫu hiện màu sai).

Một bản sửa z-order (nguồn mask luôn sơn sau các anh em bị mask) được thử
**đầu tiên** và bị hoàn tác: đa số con riêng của `Bandit` là `masking == 1`
("miễn trừ", ví dụ `Muzzle`, `Nose`, `EyeBrow`), và `BellyTexture` ban đầu
đứng trước một số trong chúng theo thứ tự file — ép "nguồn mask sau cùng" kéo
fill đặc của `BellyTexture` lên trên mắt/mõm/mũi của nhân vật luôn, đã xác
nhận sai trong ứng dụng Moho (chúng không bị ảnh hưởng, đúng như công cụ này
vốn render chúng trước bất kỳ bản sửa nào). Không có một sắp xếp lại duy nhất
các con của một container vừa thỏa "mọi `masking == 2` sau mọi `masking == 0`"
vừa "không bao giờ đổi thứ tự tương đối với bất kỳ anh em `masking == 1`"
cho tài liệu này — các ràng buộc xung đột riêng cho `BellyTexture`.

**Bản sửa thực sự đụng *hình học* mask, không phải thứ tự vẽ.** Với mỗi
shape nguồn mask có đường viền thường (không làm thon, không brush), dải
stroke riêng của nó được khắc *ra khỏi* mask — được vẽ như một stroke đen,
đúng bề rộng stroke của shape đó, trên silhouette fill trắng của mask. Bất
cứ thứ gì mask cắt khi đó không bao giờ có thể sơn vào dải đó, bất kể
z-order, nên stroke riêng của nguồn không bao giờ bị che — và các anh em
`masking == 1` không bị đụng tới (chúng chưa từng là một phần của phép tính
mask ngay từ đầu), nên không gì về hành vi đã-xác-nhận-đúng của
`Muzzle`/`Nose`/`EyeBrow` có thể hồi quy. Đo lại sau bản sửa: 62% số pixel
stroke được mẫu hiện màu riêng của `BellyTexture` (lên từ 35%), thêm 22% bị
che một cách hợp pháp bởi *các* anh em `masking == 1` khác, không liên quan
(quan hệ z-order riêng của chúng với `BellyTexture` bản sửa này đúng là để
yên), và phần còn lại không phân biệt thống kê được với phần dư còn lại ngay
cả khi bỏ hẳn `Head_DarkBlue`/`Eye_Back`/`Head_DarkBlue 2`/`Eye_Upper` khỏi
render — tức là không gán được cho các layer mục tiêu của bản sửa này, nhiều
khả năng là anti-aliasing tại ranh giới mask. Một đường viền nguồn làm thon
hoặc brush-style vẫn chỉ đóng góp fill trần của nó vào mask (hình học chưa
xác nhận cho hai trường hợp đó) — xem phần MASKING và KNOWN GAPS của module
docstring.

---

## 11. Actions và Smart Bones

"Actions" trong Moho được lưu ở hai nơi, và hai nơi trông giống nhau nhưng
làm các việc khác nhau.

### 11.1 Registry `actions` cấp layer

Hầu như mọi layer mang một danh sách `actions` có các phần tử luôn đúng
`{"name": "<action name>", "pose": 0}` — 19.921 mục như vậy trong mẫu 19-file,
với `pose` là số nguyên `0` trong từng mục. Hiện diện trên 524 của 648
`MeshLayer`, 90 của 103 `GroupLayer`, 38 của 47 `BoneLayer`, 11 của 17
`SwitchLayer`, 4 của 12 `PatchLayer`, không bao giờ trên một `TextLayer`, và
không bao giờ trên một `ImageLayer` **(cái cuối là phát hiện từ 19 file —
`ImageLayer` không tồn tại trong mẫu ban đầu)**.

Đây là một **registry tên toàn tài liệu, được nhân bản trên gần như mọi
layer**, không phải một danh sách theo-layer các action riêng của layer đó.
Bằng chứng: trong `WhatIsBone`, một `BoneLayer` tên `kafasi` với **không
bone** mang cùng 37 tên action như layer `girl` 157-bone phía trên nó. Nên
registry nói tên action nào tồn tại trong tài liệu, không phải cái nào áp
dụng ở đây.

### 11.2 Pose cấp channel

Dữ liệu hoạt ảnh thật sống trên các channel riêng lẻ. Bất kỳ channel nào ở
bất cứ đâu có thể mang danh sách `actions` riêng của nó, và ở đó `pose` là
một **channel lồng nhau đầy đủ**:

```jsonc
"actions": [
  { "name": "EyeBlink",
    "pose": { "type": "Vec2", "when": [0, 6, 12], "val": [...], "interp": [...] } }
]
```

11.816 pose như vậy tồn tại trong mẫu 19-file. Các loại channel `pose` của
chúng là `Vec2` (10.024), `Val` (1.561), `Vec3` (165), `Color` (37), `Bool`
(22), và `String` (7) — tức là một action có thể override bất kỳ loại thuộc
tính nào, kể cả màu, nhưng trong thực tế nó đa số là vị trí mesh point và
transform bone. `pose` là trường được keyframe nhiều nhất trong các tài liệu
này, bỏ xa 383 bones được keyframe của `anim_angle` ([§ 9](#9-bones-và-skinning)).

### 11.3 Actions nào là Smart Bones

Một "Smart Bone" là một bone thường được dùng như một *dial*: góc rotation
riêng của nó chọn một pose cho phần còn lại của rig.

- Một tên action đã đăng ký trở thành một **dial Smart Bone** khi nó khớp
  với `name` của một bone trong skeleton riêng của `BoneLayer` bao quanh.
- Các tên đã đăng ký không khớp bone nào là **plain actions** — các clip
  timeline tái dùng được, được kích hoạt từ cửa sổ Actions của Moho, không bị
  bone nào điều khiển. `"Walk"` của `Bandit` là ví dụ rõ nhất: 5 action đã
  đăng ký, 4 khớp tên bone, và `"Walk"` không khớp cái nào. Số đếm theo
  BoneLayer của các tên dial so với thường: `Bandit` 4/1, `kafasi` của
  `SketchBone` 9/13, `girl` của `WhatIsBone` 14/23, `Head` của `AddBone`
  27/41.
- `moho2svg.py` chỉ bao giờ kích hoạt loại dial, điều đúng — một plain action
  tắt trừ khi người dùng chạy nó, và không gì trong file nói nó đang chạy.

Khi dial `D` hoạt động, một channel mang `actions: [{"name": "D", "pose":
<channel>}]` được đọc từ `pose` thay vì `when`/`val` riêng của nó, tại một
frame được tìm bằng cách **đảo pose curve**: mảng `val` riêng của channel
pose ghi lại góc *riêng* của dial tại mỗi keyframe của pose, nên "frame pose
có góc ghi khớp góc thực hiện tại của dial" được định nghĩa rõ bằng nội suy.

Moho lưu *hai* action trên mỗi dial, một cho mỗi hướng rotation — cái thứ
hai có hậu tố `" 2"` (ví dụ `"BlinkL"` và `"BlinkL 2"`) — vì một pose curve
phải gần như đơn điệu mới đảo được. Các mẫu đầy những cặp như vậy.

Góc *hiện tại* riêng của một dial luôn là vị trí nghĩa đen của nó trên
timeline chính. Việc phân giải nó không được đệ quy vào cùng cơ chế override
mà chính nó là một phần; đây là nơi duy nhất `Channel.eval_raw()` được dùng.

### 11.4 `action_refs` và `layercomps`

`layercomps` **rỗng trong cả 19 tài liệu**, nên hình dạng phần tử của nó
không thể được tài liệu hóa từ bằng chứng này — nó là tính năng "layer comps"
của Moho (các tập show/hide có tên của các layer, được dùng để xuất các biến
thể của một tài liệu). `action_refs` rỗng trong mọi tài liệu có khóa này, và
**vắng hoàn toàn** (không chỉ rỗng) trong `Rabbit.animeproj` thế hệ `1021`
**(phát hiện từ 19 file)** — xem [§ 2](#2-cấu-trúc-cấp-cao-nhất). Nó nhiều
khả năng giữ các tham chiếu tới các action được định nghĩa bên ngoài tài
liệu này, khớp với các trường `layer_ref_*` trên các layer, nhưng đó là một
đoán, không phải một phát hiện. Không cái nào được công cụ này đọc.

---

## 12. Patch layers

Một `PatchLayer` không có trường `mesh` riêng — thay vào đó nó mang
`target_layer_uuid`, đặt tên một layer khác ở nơi khác trong tài liệu (trong
mọi ví dụ tìm thấy tới giờ, một anh em trong cùng group) mà *mesh* của nó
được tái dùng, được vẽ lại tại vị trí riêng của patch layer trong thứ tự vẽ.
Đây là cách một rig vá một đường nối thấy được giữa hai bộ phận cơ thể đè
nhau: ví dụ `ayasi-Patch` của một bàn tay tái dùng mesh lòng bàn tay `ayasi`,
nhưng nằm giữa hai layer ngón tay trong ngăn xếp thay vì dưới tất cả chúng,
nên nó che khoảng trống xuất hiện ở đó khi các ngón tay chuyển động.

`target_layer_id` cũng hiện diện cùng `target_layer_uuid` trên toàn bộ 8
patch layers, với các giá trị `0` (4×), `1`, `2`, `3`, và `7` — nên nó không
phải hằng số `0` mà một bản sửa cũ của tài liệu này báo cáo. Mục đích của nó
ngoài uuid vẫn chưa biết, và công cụ này bỏ qua nó.

**Các `transforms`/`parent_bone`/`flexi_bone_subset`/`origin` riêng của patch
layer không được dùng khi render nó**, dù chúng hiện diện và trông như đáng
lẽ quan trọng. Đã xác nhận theo kinh nghiệm: mọi `PatchLayer` tìm thấy khắp
các tài liệu tham chiếu mang một transform riêng kỳ lạ, có vẻ không liên
quan (ví dụ một tỷ lệ Y không đều `0.147` cộng một rotation 8,9° trên
`ayasi-Patch` của một bàn tay; một tỷ lệ đều `~0.49` trên
`Leg_L-Patch`/`Leg_R-Patch` trong một rig khác), trong khi *target* của nó
nhất quán có transform đơn vị (`scale: 1`, `translation: 0`). Render với
transform riêng của patch tái tạo đúng như vậy: một mảnh vụn bị bẹp trôi
xa khỏi nơi target thực sự render. Transform của target (và
`parent_bone`/`flexi_bone_subset`/`origin`) được dùng thay vào đó — tức là
một patch layer đã phân giải render như một bản sao của target của nó, chỉ
tại một điểm khác trong thứ tự vẽ. Đây là một **heuristic**, không phải một
dịch ngược đã xác nhận chính xác — không có bản xuất SVG Moho độc lập nào
của một tài liệu dùng `PatchLayer` để đối chiếu pixel-từng-pixel.

**Một patch đã phân giải nhân đôi fill của target của nó thôi, không bao giờ
đường viền của nó.** Phần này *đã* được xác nhận trực tiếp với ứng dụng Moho
(không chỉ với đầu ra riêng của công cụ này), trên hai điểm được chọn riêng
để loại trừ một yếu tố gây nhiễu: `ayasi-Patch` (`masking == 2`, một nguồn
mask) và `Left Bicep-Patch` (`masking == 0`, không phải nguồn mask) — cả hai
đều là `PatchLayer` có target với `has_outline: true` và một stroke thật, và
**cả hai không hiện stroke nào trong canvas của chính Moho** trong khi các
target của chúng thì có. Vì `masking` khác nhau giữa hai cái nhưng kết quả
không khác, sự ức chế gắn với việc là một `PatchLayer`, không phải với
`masking` (thứ § 10 đã xác nhận vẫn vẽ các layer nguồn-mask của nó bình
thường). `moho2svg.py` cài đặt điều này qua `ShapeGroupRenderer.suppress_outline`,
được đặt bất cứ khi nào layer được render là một `PatchLayer` — không phải
bằng cách sửa `Shape.has_outline` chính nó, vì một patch và target của nó
dùng chung đúng các đối tượng `Shape`/`Mesh`, và target vẫn phải vẽ đường
viền riêng của nó bất cứ nơi nào *nó* render trong cây.

---

## 13. Tóm tắt mức độ bao phủ

Công cụ này đọc gì, trong nháy mắt. "Được khai thác" nghĩa là ít nhất một
trong 19 tài liệu mẫu có một giá trị khác mặc định cho nó, nên bỏ qua nó
thay đổi đầu ra tham chiếu hiện tại trong `svg/`.

### 13.1 Được đọc và áp dụng

| Khu vực | Các trường |
|---|---|
| Tài liệu | `version`, `project_data.width`/`.height`, `styles`, `layers` |
| Layer | `type`, `name`, `visible`, `edit_only`, `layers`, `uuid`, `origin`, `parent_bone`, `flexi_bone_subset`, `masking`, `group_mask`, `actions`, `transforms.translation`/`.scale`/`.rotation_z`/`.flip_h`/`.flip_v` |
| Switch | `switch_keys` |
| Patch | `target_layer_uuid` |
| Text | `mesh_layer` |
| Mesh | `points[].position`/`.width`, `curves[].closed`/`.points[]` (`point`, `smoothness`, `weight_in`/`out`, `offset_in`/`out`, `segments_on`), `shapes[]` (`edges`, `has_fill`, `has_outline`, `style`, `inherited_style*`, `id`, `combo_mode`, `effect_scale`, `effect_rotation`) |
| Style | `name`, `uuid`, `define_fill_color`/`_line_col`/`_line_width`, `fill_color`, `line_color`, `line_width`, `line_caps`, `fill_style` (`gradient_type`, `gradients[].location`/`.color`), `brush_name`, `brush_jitter`, `brush_spacing`, `brush_align`, `brush_tint` |
| Bone | `name`, `parent`, `length`, `strength`, `anim_pos`, `anim_angle`, `anim_scale` |
| Channel | `when`, `val`, `actions[].name`/`.pose` |

### 13.2 Bị bỏ qua **và được các mẫu khai thác** — các khác biệt đầu ra thật

Xếp hạng theo mức độ thấy được của khác biệt:

1. `Rabbit.animeproj` (thế hệ định dạng `1021`) không có
   `weight_in`/`weight_out`/`offset_in`/`offset_out` trên bất kỳ curve point
   nào, nên mọi tay nắm được tái dựng từ giá trị mặc định trung tính thay vì
   giá trị lưu trong file. ([§ 7.3](#73-curves-và-curve-points)) Tài liệu tải
   và xuất được; thứ chưa kiểm chứng là *hình dạng* tay nắm, vì không có SVG
   tham chiếu cho nó. **(Phát hiện từ 19 file.)** *(Trước khi thêm phần lùi về
   mặc định bằng `.get()`, đây là một lỗi cứng khi tải —
   `KeyError: 'weight_in'` — không phải một khoảng trống độ chính xác render.)*
2. `layer_effects.alpha` — 9 layers đáng lẽ 60% đặc. ([§ 6.3](#63-các-trường-chung-ảnh-hưởng-render-và-không-được-dùng))
3. `blend_mode: 1` — 16 layers hòa trộn không bình thường. ([§ 6.3](#63-các-trường-chung-ảnh-hưởng-render-và-không-được-dùng))
4. `ImageLayer` — 15 layers (một tài liệu) âm thầm mất toàn bộ artwork raster
   của chúng, vì đây là một exporter chỉ-vector. **(Phát hiện từ 19 file.)**
   ([§ 6.5](#65-imagelayer-phát-hiện-từ-19-file))
5. `style.fill_style` / `.line_style` / `.fill_style2` giữ `SS_Crayon`,
   `SS_Soft`, `SS_Shadow`, hoặc `SS_Texture2` — 43 lần xuất hiện tổng cộng
   trong 6 file render như một fill/stroke phẳng thay vì effect textured,
   blurred, shadowed, hoặc textured-fill của Moho. **(Phát hiện từ 19 file,
   thay thế mục "25 styles viền với một gradient" ban đầu — số đếm đó giờ là
   116 lần xuất hiện `SS_Gradient2`, cộng 43 lần không-gradient này.)**
   ([§ 8.3](#83-các-biến-thể-effect-style-phát-hiện-từ-19-file))
6. `extra_sketchy` / `extra_lines: 5` — 2 layers đáng lẽ vẽ các stroke nhấp
   nhô lặp lại. ([§ 6.4](#64-các-trường-riêng-theo-loại))
7. `channel.interp` — timing phi tuyến trên `pose`/`anim_*`; chính xác tại
   các keyframe, lệch giữa chúng. Chỉ quan trọng cho một `--frame N` không
   phải một keyframe. ([§ 5.3](#53-các-mục-interp))
8. `bone.scaling_mode: 2` — 242 bones; có thể liên quan tới tỷ lệ bone bất
   đối xứng được giữ lại. ([§ 9](#9-bones-và-skinning))
9. `mesh.curve_interpretation: 0` — 2 mesh khác phần còn lại. ([§ 7.1](#71-đối-tượng-mesh))
10. `shape.fill_allowed: false` — 859 shapes (tổng 19-file, tăng từ 229 trong
    mẫu ban đầu). Tương tác với `has_fill` chưa giải mã. ([§ 7.4](#74-shapes-và-edges))
11. `style.line_caps: 0` — 765 styles (3 tài liệu) dùng butt caps thay vì
    round caps mà mẫu 5-file ban đầu chỉ toàn thấy. **(Phát hiện từ 19 file.)**
    Liệu ánh xạ `0` của `LINE_CAP_NAMES` có thực sự đúng hay không chưa được
    kiểm chứng. ([§ 8.1](#81-named-styles-docstyles))

Stroke riêng của một anh em masking==2 vẫn thấy trên thứ nó mask cũng từng
trong danh sách này cho tới khi nó được sửa (hình học mask giờ loại trừ dải
stroke thường riêng của mỗi shape nguồn — xem [§ 10](#10-masking)); một đường
viền nguồn làm thon hoặc brush-style là khoảng trống duy nhất còn lại ở đó.

Đường viền riêng của một thành viên `combo_mode == 3` từng cũng hiện một
khoảng trống thật mà Moho không vẽ — đã xác nhận trên `Eye_Upper`/`S3` của
`Bandit` — vì công cụ này xấp xỉ phép boolean bằng SVG masking thay vì một
giao điểm path thật. Nay đã sửa bằng cách vẽ đường viền đầy đủ của một thành
viên như vậy (thay vì bỏ segment ẩn của nó) và để clip intersect hiện có cắt
nó đúng cách, né nhu cầu giao điểm Bezier–Bezier thật; xem
[§ 7.8](#78-kết-hợp-shape-boolean) cho phát hiện đầy đủ.

Các mục 8–10 là *chưa giải mã*, không phải *biết-sai*: các mẫu đặt chúng tới
một giá trị khác mặc định, nhưng không gì chứng minh đầu ra hiện tại sai cho
chúng.

### 13.3 Bị bỏ qua và **không** được khai thác — các khoảng trống chưa kiểm thử

Hiện diện trong định dạng, nhưng tại các giá trị mặc định khắp các mẫu, nên
bỏ qua chúng hiện vô hình: `channel.mute`, `channel.split`,
`bone.anim_parent` (thừa với `parent` trên toàn bộ 850 bones — xem
[§ 9](#9-bones-và-skinning)),
`doc.animated_values` (camera), `curve.start_percent`/`end_percent`, curve
profiles, `point.colored`/`color`/`opacity`, `layer_effects.visibility` và
năm channel effect kia, `layer_outline`, `layer_shadow`,
`layer_shading`, `perspective_shadow`, `layer_color`, `motion_blur`,
`timing_offset`, fill/line textures, `layer_ref_*`,
`distortion_layer_uuid`, các trường follow-path, mọi trường physics (kể cả
`gravity`/`wind` — xem [§ 6.4](#64-các-trường-riêng-theo-loại)), mọi trường
constraint/IK của bone, `project_data.global_render_style_*`, `mesh.groups`,
`mesh.shape_order`, `shape.3d_thickness`/`effect_offset`/`combo_blend_anim`,
`quality_flags`, `Mesh3DOptions`/`3d_mode`
**(phát hiện từ 19 file — xem [§ 6.4](#64-các-trường-riêng-theo-loại))**,
`parent_bone == -3` **(phát hiện từ 19 file, chỉ `ImageLayer`)**, `masking ==
5`/`6` **(phát hiện từ 19 file)**, và các trường font/balloon của `TextLayer`.

`layer_ordering`/`animated_layer_order` di chuyển từ "chưa kiểm thử" sang
**xác-nhận-trơ-trong-mẫu-này (phát hiện từ 19 file)**: giá trị của channel là
một chuỗi rỗng trong toàn bộ ~150 instance được mẫu, nên render thứ tự-cố
định của công cụ này xác minh được là đúng cho mọi tài liệu ở đây, không chỉ
là chưa được khai thác — xem [§ 6.4](#64-các-trường-riêng-theo-loại).

Hai trường bone/rig từng nằm trong danh sách này đã rời khỏi nó, vì chúng
**không** tại các mặc định của chúng ở mọi nơi: `skeleton.binding_mode`
(`2` trên một skeleton) và `bone.offset` (khác không trên 5 bones). Cả hai
giờ được xếp là các điều-chưa-biết-đã-biết trong [§ 14](#14-các-điều-chưa-biết-đã-biết).

Rủi ro nhất trong số này là những cái một tài liệu sản xuất thật sẽ hợp lý
mà dùng: **`layer_effects.visibility`** (show/hide hoạt ảnh),
**`curve.end_percent`** (một đường tự vẽ lên chính nó), **`timing_offset`**,
**`project_data.global_render_style_*`**, và **các channel camera**.

---

## 14. Các điều chưa biết đã biết

Đây là một công việc dịch ngược vẫn đang tiếp diễn, không phải một đặc tả. Các
trường có *giá trị* được quan sát thấy nhưng *ý nghĩa* chưa được giải mã:

- `combo_mode: 2` — được báo trong module docstring, vắng trong cả 19 tài
  liệu mẫu. ([§ 7.8](#78-kết-hợp-shape-boolean))
- `channel.interp.t` / `.im` / `.in` / `.s` / `.h` / `.v1` / `.v2` / `.b` —
  enum loại nội suy và các tham số của nó. ([§ 5.3](#53-các-mục-interp))
- `channel.ref` — `true` trên 207 channel trong 3 tài liệu; ý nghĩa chưa
  giải mã. **(Phát hiện từ 19 file, đính chính một phát biểu "false ở mọi
  nơi" trước đó — xem [§ 5.1](#51-các-trường-của-đối-tượng-channel).)**
- `group_mask: 1` so với `2` — 2 containers dùng `1`. ([§ 10](#10-masking))
- `masking: 5` / `6` — 7 layers trong 3 tài liệu. **(Phát hiện từ 19 file.)**
  ([§ 10](#10-masking))
- `parent_bone: -3` — 9 instance `ImageLayer`, luôn với một `flexi_bone_subset`
  thật. **(Phát hiện từ 19 file.)** ([§ 6.2](#62-các-trường-chung-ảnh-hưởng-render-và-được-dùng))
- Đóng góp mask đúng của một anh em `masking == 2` có đường viền riêng làm
  thon hoặc brush-style (một stroke đều thường được xử lý — xem
  [§ 10](#10-masking)).
- `blend_mode: 1` — 16 layers. ([§ 6.3](#63-các-trường-chung-ảnh-hưởng-render-và-không-được-dùng))
- `bone.scaling_mode` (`0`/`2`), `skeleton.binding_mode` (`1` trên 41
  skeletons, `2` trên một — **đính chính một phát biểu "luôn `1`" trước đó**),
  `bone.offset` (khác không trên 5 bones — xem [§ 9](#9-bones-và-skinning)),
  `bone.fixed_angle` ("independent angle", `true` trên 45 bones; kết quả đã
  đã bake vào `anim_angle` hay chưa thì chưa kiểm chứng),
  `mesh.curve_interpretation` (`0`/`1`), `quality_flags` (một bit field),
  `face_camera_mode` (luôn `2`), `shape.fill_allowed`,
  `PatchLayer.target_layer_id`, `fill_style_id`/`line_style_id`/
  `fill_style2_id` (đa số `9`; cũng có `12`, `11`, `2`, `10` — **các giá trị
  không-phải-9 là phát hiện từ 19 file**).
- Hình dạng phần tử `layercomps` và `action_refs` — cả hai danh sách rỗng
  trong mọi tài liệu có khóa này. ([§ 11.4](#114-action_refs-và-layercomps))
- Số đầu tiên của một hậu tố `brush_name` kiểu cũ.
  ([§ 8.6](#86-phân-giải-brush_name-thành-một-file))
- Ý nghĩa trường riêng của `Mesh3DOptions` (`3d_shading_mode`,
  `3d_shading_density`, các công tắc crease/edge) — hiện diện trên mọi
  `MeshLayer` nhưng hoàn toàn trơ vì `3d_mode` là `0` ở mọi nơi. **(Phát hiện
  từ 19 file.)** ([§ 6.4](#64-các-trường-riêng-theo-loại))
- Các trường cel-shading `toon_*` của `ImageLayer`, `sampling_mode`,
  `quality_level` — một toàn bộ loại layer không được mô hình hóa chút nào.
  **(Phát hiện từ 19 file.)** ([§ 6.5](#65-imagelayer-phát-hiện-từ-19-file))
- Nội bộ `SS_Crayon`/`SS_Soft`/`SS_Shadow`/`SS_Texture2` — `rand_seed`,
  `clear_background`, `reduce_randomization`, `fill_mode`, và sự tương tác
  giữa `fill_style` và `fill_style2` của một shape khi cả hai hiện diện.
  **(Phát hiện từ 19 file.)** ([§ 8.3](#83-các-biến-thể-effect-style-phát-hiện-từ-19-file))
- Các công tắc boolean `g_<number>` và `psd_layers` trong túi `metadata`
  riêng của một layer. **(Phát hiện từ 19 file.)** ([§ 6.4](#64-các-trường-riêng-theo-loại))
- **Smart Warp** — một toàn bộ tính năng biến dạng Moho **không có biểu diễn
  nào trong mẫu này**: một tìm kiếm bất kỳ khóa JSON nào chứa "warp" trả về
  không lượt truy cập nào khắp cả 19 file. Các móc duy nhất thấy được là
  `distortion_layer_uuid` (rỗng ở mọi nơi) và các cờ chỉ-`1045`
  `triangulated` / `squashable_deformer` / `frame_zero_deformer`. Một tài
  liệu dùng nó sẽ xuất với biến dạng bị bỏ âm thầm. Xem
  [`moho-rigging-and-deformation.md` § 5](moho-rigging-and-deformation.md#5-smart-warp).

Cộng các xấp xỉ đã ghi chú: độ chính xác vị trí gradient, hình dạng suy giảm
trọng số bone mềm cho ảnh hưởng đè nhau, heuristic transform `PatchLayer`
([§ 12](#12-patch-layers)), và các đơn giản hóa stroke cọ
([§ 8.5](#85-kiểu-cọ)).

Xem phần KNOWN GAPS của module docstring cho danh sách phía render. Nếu bạn
tìm một tài liệu thật mâu thuẫn điều gì đó ở đây, hãy ưu tiên bằng chứng
trong tài liệu hơn những gì được viết trong file này — và nói rõ điều đó, vì
mọi số đếm trên được đo từ 19 file, không phải từ toàn bộ không gian đầu ra
khả dĩ của Moho. Một đối tác cấu trúc kiểm tra bằng máy được — một JSON
Schema với kiểm toán mức đầy đủ riêng — sống trong `schema/`; xem
`schema/README.md` § 3 cho cách kiểm toán đó hoạt động và nó còn bắt thêm gì.
