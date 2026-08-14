# Lottie và ThorVG

> Bản dịch tiếng Việt của `docs/lottie-and-thorvg.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Lottie là một định dạng file JSON cho đồ họa vector hoạt ảnh. ThorVG là một
engine C++ có thể đọc một file như thế và vẽ nó. Tài liệu này mô tả cả hai, và
mối quan hệ giữa chúng, làm nền tảng cho một tính năng dự kiến: **xuất một
frame cụ thể ra khỏi một file Lottie**.

Khác với định dạng Moho, Lottie **có tài liệu chính thức và máy đọc được**.
Repo này giữ một bản sao tài liệu đó dưới dạng JSON Schema, nên gần như không
có gì ở đây phải dịch ngược. Chỗ nào tài liệu này nói theo schema thì đó là dữ
kiện, bạn kiểm lại được bằng một script ngắn. Chỗ nào lấy từ một trang web bên
ngoài hoặc từ file nguồn tải trên GitHub thì sẽ được ghi rõ.

Các tài liệu đồng hành (phía Moho, không bị tài liệu này sửa đổi):

- [`moho-project-file-format.md`](moho-project-file-format.md) — tài liệu tra
  cứu các trường của Moho.
- [`moho-animation-and-transform.md`](moho-animation-and-transform.md) — cách
  Moho lưu chuyển động và ghép transform.
- [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md) —
  bones, skinning, Smart Warp.
- [`moho-export-pipeline.md`](moho-export-pipeline.md) — cách `moho2svg.py`
  duyệt một tài liệu và sinh ra SVG.
- [`moho-exporting-svg.md`](moho-exporting-svg.md) — hướng dẫn sử dụng CLI.

Mục 14 là nơi duy nhất hai thế giới gặp nhau. Các mục 1 đến 8 là thuần Lottie,
các mục 9 đến 13 là thuần ThorVG và tích hợp.

---

## 1. Phạm vi và cơ sở bằng chứng

### 1.1 Những gì đã được kiểm chứng

Mọi tên trường, kiểu, giá trị mặc định và giá trị enum của Lottie trong các
mục 2 đến 8 đều đọc ra từ các file schema nằm trong repo này:

| Đường dẫn | Là gì | Quy mô |
|---|---|---|
| `lottie/lottie.schema.json` | Một file JSON Schema gộp sẵn, tự chứa đủ | 12 module, 159 định nghĩa |
| `lottie/schema/**` | Cũng schema đó, tách ra mỗi định nghĩa một file | 160 file (159 định nghĩa + `root.json`) |
| `lottie/examples/` | Hai tài liệu Lottie mẫu | không dùng làm nguồn trong tài liệu này |

**Cả hai dạng schema đều được track trong git; `lottie/examples/` thì không.**
Nên một bản clone mới vẫn chạy lại được mọi script ở § 16, kể cả script so
sánh bản gộp với bản tách. Không có gì trong tài liệu này phụ thuộc vào các
file mẫu.

Hai dạng schema đã được so sánh bằng script. Sau khi chuẩn hóa đích của `$ref`
và bỏ khóa `$schema` / `$id` riêng của từng file, **157 trên 159 định nghĩa
giống hệt nhau đến từng byte**. Hai cái khác nhau là `layers/unknown-layer` và
`shapes/unknown-shape`; § 2.4 giải thích vì sao, và khác biệt này quan trọng
nếu bạn định validate file.

### 1.2 Những gì chưa kiểm chứng

- **Không có file Lottie nào được render** trong lúc viết tài liệu này. Không
  có khẳng định nào ở đây về kết quả hiển thị.
- **ThorVG chưa được build, cài đặt hay chạy.** Các mục 9, 10 và 12 mô tả API
  đúng như nó được công bố trong mã nguồn và trang web ThorVG; đó không phải
  quan sát từ một bản build chạy thật trong repo này.
- **Các file `lottie/examples/` cố ý không được dùng.** Một file mẫu chỉ cho
  thấy một exporter nào đó tình cờ xuất ra cái gì. Schema mới cho thấy định
  dạng cho phép những gì.

### 1.3 Các nguồn bên ngoài

| Nguồn | Được dùng cho |
|---|---|
| `https://lottiefiles.github.io/lottie-docs/` | Tài liệu Lottie dành cho người đọc; đây là nguồn gốc của schema trong repo này (§ 2.1) |
| `https://lottie.github.io/lottie-spec/` | Nhánh tài liệu Lottie còn lại (§ 11.1) |
| `https://www.thorvg.org/` | ThorVG là gì: định dạng, backend, nền tảng |
| `thorvg/thorvg` trên GitHub (`src/bindings/capi/thorvg_capi.h`, `meson_options.txt`, `tools/`) | Chữ ký hàm C API chính xác, các tùy chọn build, các công cụ đi kèm |
| `thorvg/thorvg.example` trên GitHub (`src/Lottie.cpp`) | Cách dùng C++ chuẩn mực của API animation |
| `laggykiller/thorvg-python` (GitHub + metadata PyPI) | Binding Python được đánh giá trong § 13 |

Các nhãn độ tin cậy dùng bên dưới: **[confirmed]** nghĩa là đọc trực tiếp từ
một file trong repo này hoặc từ một file nguồn đã trích ở trên; **[reported]**
nghĩa là do một trang web nói ra và chưa kiểm chứng độc lập; **[inferred]**
nghĩa là kết luận rút ra từ những cái đó, không phải trích dẫn.

---

## 2. Cách đọc schema Lottie

### 2.1 Đây là schema nào

`lottie/lottie.schema.json` khai báo:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lottiefiles.github.io/lottie-docs/schema/lottie.schema.json",
  "$ref": "#/$defs/composition/animation"
}
```

[confirmed] Vậy đây là schema **lottie-docs**, được LottieFiles phát hành. Nó
được viết bằng **JSON Schema draft 2020-12**, và toàn bộ tài liệu chỉ là một
`$ref` trỏ tới một định nghĩa: `composition/animation`. Mọi thứ khác móc vào
đó.

`lottie/schema/root.json` cũng đúng ba dòng đó, trong cây tách nhỏ. [confirmed]

Đây *không phải* schema Lottie duy nhất trên thế giới. Xem § 11.1 để phân biệt
lottie-docs với lottie-spec — điều này quan trọng khi bạn cần quyết định thế
nào là "Lottie hợp lệ".

### 2.2 Bố cục `$defs`

Mọi định nghĩa nằm dưới `$defs`, chia thành 12 module. Các con số dưới đây là
số đếm thật. [confirmed]

| Module | Số định nghĩa | Chứa gì |
|---|---:|---|
| `composition` | 5 | gốc tài liệu, metadata, motion blur |
| `layers` | 14 | 9 loại layer cụ thể cộng các base dùng chung |
| `shapes` | 29 | mọi thứ có thể xuất hiện bên trong một shape layer |
| `properties` | 17 | bộ máy property động và keyframe |
| `values` | 7 | các kiểu giá trị lá (color, vector, bezier, …) |
| `helpers` | 6 | transform, mask, marker, slot, visual object |
| `assets` | 7 | precomposition, images, sounds, data sources |
| `constants` | 20 | các enum |
| `effects` | 18 | các layer effect kiểu After Effects |
| `effect-values` | 11 | các loại tham số mà những effect đó nhận |
| `styles` | 11 | các layer style kiểu Photoshop |
| `text` | 14 | text documents, fonts, text animators |

Một tham chiếu trong file gộp trông như `#/$defs/shapes/fill`. Trong cây tách
nhỏ, cũng tham chiếu đó lại là một đường dẫn file tương đối. Đó là khác biệt
mang tính hệ thống duy nhất giữa hai dạng.

### 2.3 Cách ghép định nghĩa (composition)

Định nghĩa trong Lottie được dựng bằng cách ghép lại, không phải bằng lặp lại.
Hầu như mọi đối tượng đều là một `allOf` gồm một base dùng chung cộng các
trường riêng của nó. Chuỗi ghép của một fill màu đặc là:

```
shapes/fill
  allOf[0] -> shapes/shape-style      (adds: o = opacity)
                allOf[0] -> shapes/graphic-element   (adds: nm, mn, hd, ty, bm, ix, cl, ln)
                              allOf[0] -> helpers/visual-object  (adds: nm, mn)
  allOf[1] -> own fields              (ty = "fl", c = color, r = fill rule)
```

[confirmed] Hệ quả thực tế: **đọc một định nghĩa thôi thì chưa đủ biết một đối
tượng chấp nhận những trường nào.** Bạn phải lần theo chuỗi `allOf` về tới
gốc. Một bộ đọc chỉ xử lý hai trường riêng của `shapes/fill` sẽ âm thầm bỏ sót
`hd` (ẩn) và `bm` (blend mode) — hai thứ làm thay đổi cái được vẽ.

### 2.4 Trường phân biệt kiểu, và lối thoát

Các danh sách đa hình được mô tả bằng `oneOf` trên các kiểu cụ thể, phân biệt
nhau bằng trường `ty`:

- `layers/all-layers` — `oneOf` của 10 mục, mục cuối là `layers/unknown-layer`.
- `shapes/all-graphic-elements` — `oneOf` của 20 mục, mục cuối là
  `shapes/unknown-shape`.
- `assets/all-assets` — `oneOf` của 4 mục, không có fallback unknown.

[confirmed] Các mục `unknown-*` tồn tại để một file dùng một giá trị `ty` mà
schema không biết vẫn validate được. Chúng được viết như một phép phủ định:

```json
"ty": { "not": { "$comment": "enum list is dynamically generated",
                 "enum": [0, 1, 2, 3, 4, 5, 6, 15, 13] } }
```

[confirmed] **Đây là chỗ duy nhất file gộp và cây tách nhỏ không khớp nhau.**
Trong cây tách nhỏ, các mảng `enum` đó rỗng; file gộp thì điền đầy. Một `enum`
rỗng nằm trong `not` sẽ không khớp gì cả, nên ở cây tách nhỏ `unknown-layer`
lại chấp nhận *mọi* `ty`, kể cả những `ty` đã biết — khi đó `oneOf` khớp hai
nhánh cùng lúc và validate hỏng.

**Hãy dùng `lottie/lottie.schema.json` để validate.** Cây tách nhỏ là bản
nguồn để chỉnh sửa; file gộp là kết quả build. [inferred, nhưng chuyện `enum`
rỗng so với `enum` đầy thì đã xác nhận trực tiếp]

### 2.5 Một lưu ý về từ "required"

Schema đánh dấu rất ít thứ là required. Ví dụ `layers/layer` chỉ yêu cầu `ty`,
`ip`, `op`; `helpers/transform` không yêu cầu gì cả. [confirmed] Đó là chuyện
*validation*, không phải chuyện *render*. Renderer vẫn phải tự cấp giá trị mặc
định cho mọi thuộc tính bị thiếu, mà schema thì chỉ thỉnh thoảng mới ghi mặc
định (`sr` mặc định `1`, `st` mặc định `0`, `bm` mặc định `0`, mask `o` mặc
định `100`). Chỗ nào schema không nêu mặc định thì bạn phải lấy từ hành vi của
player, không lấy từ schema.

---

## 3. Gốc của tài liệu

Toàn bộ file là một đối tượng `composition/animation`. Nó là một `allOf` của
`helpers/visual-object` (cho `nm` và `mn`) cộng các trường này. [confirmed]

| Khóa | Kiểu | Tiêu đề | Ghi chú từ schema |
|---|---|---|---|
| `v` | string | Bodymovin version | "on very old versions some things might be slightly different from what is explained here" |
| `ver` | integer | Specification Version | 6 chữ số, `MMmmpp`; tối thiểu 10000 |
| `fr` | number | Framerate | khung hình mỗi giây, phải lớn hơn 0 |
| `ip` | number | In Point | "Frame the animation starts at (usually 0)" |
| `op` | number | Out Point | "Frame the animation stops/loops at, which makes this the duration in frames when `ip` is 0" |
| `w` | integer | Width | tối thiểu 0 |
| `h` | integer | Height | tối thiểu 0 |
| `ddd` | int-boolean | Threedimensional | mặc định 0; hoạt ảnh có layer 3D hay không |
| `assets` | array | Assets | danh sách `assets/all-assets` |
| `comps` | array | Extra Compositions | precomposition không được thứ gì tham chiếu |
| `fonts` | `text/font-list` | Fonts | |
| `chars` | array | Characters | "If present a player might only render characters defined here and nothing else" |
| `meta` | `composition/metadata` | Metadata | tác giả, mô tả, màu chủ đề, generator, từ khóa |
| `metadata` | `composition/user-metadata` | User Metadata | tên file, các thuộc tính tùy biến |
| `mb` | `composition/motion-blur` | Motion blur | shutter angle/phase, samples per frame, adaptive sample limit |
| `slots` | object | Slots | xem § 7.4 |
| `markers` | array | Markers | xem § 8.4 |

Chú ý hai trường phiên bản khác nhau. `v` là phiên bản **exporter Bodymovin**
(một chuỗi như `"5.7.0"`); `ver` là một phiên bản **đặc tả** được mã hóa như
một số nguyên. Chúng trả lời các câu hỏi khác nhau, và một file có thể mang
một, cả hai, hoặc không cái nào. [confirmed]

`composition/composition` là một định nghĩa riêng, rất nhỏ: một đối tượng có
mảng `layers` bắt buộc. Cả gốc animation lẫn mọi asset precomposition đều bao
gồm nó. [confirmed]

---

## 4. Properties và keyframes

Đây là phần Lottie quan trọng nhất với tính năng xuất frame, vì "cho tôi frame
N" nghĩa là "tính mọi property tại frame N".

### 4.1 Lớp vỏ chung của property

`properties/property` là base dùng chung: [confirmed]

| Khóa | Ý nghĩa |
|---|---|
| `a` | Cờ có hoạt ảnh hay không, kiểu int-boolean, mặc định 0 |
| `k` | Giá trị — một giá trị tĩnh khi `a == 0`, một mảng keyframes khi `a == 1` |
| `ix` | Chỉ số property, dùng cho expression |
| `x` | Expression, một chuỗi |
| `sid` | Slot id — nếu hiện diện, giá trị đến từ `slots` của tài liệu |

Base có một điều kiện: `if` đối tượng có `sid` thì không bắt buộc gì thêm;
`else` thì cả `a` lẫn `k` đều bắt buộc. [confirmed] Nên một property vẫn hợp lệ
khi **không có giá trị riêng** mà nhường cho một slot.

Mỗi kiểu property cụ thể là một `allOf` gồm base đó cộng một `oneOf` của hai
dạng — dạng không hoạt ảnh (`a` const 0, `k` là một giá trị) và dạng có hoạt
ảnh (`a` const 1, `k` là mảng keyframe). Các kiểu:

| Định nghĩa | `k` khi tĩnh | Phần tử của `k` khi có hoạt ảnh |
|---|---|---|
| `scalar-property` | `number` | `vector-keyframe` |
| `vector-property` | `values/vector` | `vector-keyframe` |
| `position-property` | `values/vector` | `position-keyframe` |
| `color-property` | `values/color` | `color-keyframe` |
| `bezier-property` | `values/bezier` | `bezier-keyframe` |
| `gradient-stops` | `values/gradient` | `gradient-keyframe` |

[confirmed] Có hai chỗ lạ đáng chú ý. `scalar-property` khi tĩnh thì giữ một
`number` thường, nhưng keyframe của nó lại là keyframe **vector**, nên `s` của
một scalar có hoạt ảnh là mảng kiểu `[42]`, chứ không phải số trần `42`. Và
`vector-property` / `position-property` nhận thêm trường `l` ("Length") — số
thành phần — chỉ dùng khi expression đọc giá trị. [confirmed]

### 4.2 Keyframes

`properties/base-keyframe` chỉ yêu cầu `t`: [confirmed]

| Khóa | Ý nghĩa |
|---|---|
| `t` | Thời điểm, tính bằng **số frame** (không phải giây), mặc định 0 |
| `h` | Cờ hold, int-boolean, mặc định 0 |
| `i` | Tiếp tuyến vào — easing đi *vào keyframe kế tiếp*, kiểu `easing-handle` |
| `o` | Tiếp tuyến ra — easing rời *khỏi keyframe hiện tại*, kiểu `easing-handle` |

Mọi keyframe cụ thể đều thêm `s` — giá trị tại keyframe này — và `e` **đã bỏ
(deprecated)** — giá trị ở cuối đoạn. Schema nói thẳng quy tắc này: "note that
this is deprecated and you should use `s` from the next keyframe to get this
value". [confirmed] Bộ đọc chỉ nên coi `e` là phương án dự phòng cho file
cũ.

`position-keyframe` mở rộng `vector-keyframe` bằng `ti` và `to` — tiếp tuyến
trong không gian *giá trị*: "Tangent for values (eg: moving position around a
curved path)". [confirmed] Chính hai cái này làm một vị trí chạy theo đường
cong thay vì đường thẳng. Chúng tách biệt với easing `i` / `o`, vốn tác động
lên thời gian.

`bezier-keyframe` có một ràng buộc lạ: `s` của nó là **mảng đúng một phần tử**
kiểu `values/bezier` (`minItems: 1, maxItems: 1`). [confirmed] Một shape
keyframe là mảng một phần tử bọc lấy path, chứ không phải chính path.

### 4.3 Easing

`properties/easing-handle` yêu cầu `x` và `y`, mỗi cái *hoặc* là một số *hoặc*
là một mảng các số. [confirmed] Lời của chính schema:

- `x` — "Time component: 0 means start time of the keyframe, 1 means time of
  the next keyframe." Bị giới hạn trong `[0, 1]`.
- `y` — "Value interpolation component: 0 means start value of the keyframe,
  1 means value at the next keyframe." Không bị giới hạn trong `[0, 1]`, nên
  overshoot là hợp lệ.

Vậy phép nội suy của một đoạn là một đường Bezier bậc ba trong không gian
(thời gian, giá trị) đã chuẩn hóa, với điểm điều khiển `(o.x, o.y)` lấy từ
keyframe trước và `(i.x, i.y)` lấy từ keyframe sau. Dạng mảng có mặt để mỗi
thành phần của một giá trị nhiều thành phần được ease khác nhau. [inferred từ
định nghĩa kiểu; schema không viết rõ ngữ nghĩa theo từng thành phần]

Khi `h` (hold) bằng 1 ở một keyframe, giá trị giữ nguyên cho tới keyframe kế
tiếp. [inferred từ tên trường và kiểu int-boolean; schema không có mô tả nào
cho `h`]

### 4.4 Các kiểu giá trị lá

`values/*` là các lá cụ thể. [confirmed]

| Định nghĩa | Dạng dữ liệu |
|---|---|
| `vector` | mảng các số, không có ràng buộc độ dài |
| `color` | mảng 3 hoặc 4 số, **mỗi số trong `[0, 1]`** |
| `gradient` | mảng phẳng các số trong `[0, 1]`: các stop màu `[offset, r, g, b]` trước, rồi các stop độ trong suốt tùy chọn `[offset, alpha]` |
| `bezier` | đối tượng gồm `c` (khép kín, mặc định false), `v` (đỉnh), `i` (tiếp tuyến vào), `o` (tiếp tuyến ra); `i`, `v`, `o` đều bắt buộc |
| `int-boolean` | số nguyên, enum `[0, 1]` |
| `hexcolor` | chuỗi khớp `^#([a-fA-F0-9]{6})$` |
| `data-url` | chuỗi khớp `^data:([\w/]+)(;base64)?,(.+)$` |

Hai điều ở đây rất dễ làm sai.

**Màu là số thực 0..1, không phải 0..255** — trừ `layers/solid-layer.sc`, vốn
là một chuỗi `hexcolor`. [confirmed] Lottie chỉ thiếu nhất quán ở đúng một chỗ
này.

**Các tiếp tuyến Bezier là tương đối.** Schema nói các điểm `i` và `o` "are
along the `in`/`out` tangents **relative to** the corresponding `v`".
[confirmed] Nên điểm điều khiển tuyệt đối của đường cong bậc ba là
`v[n] + o[n]`, chứ không phải `o[n]`. Đây đúng là quy ước Moho dùng sau khi
`BezierReconstructor` chạy xong, và khác với dữ liệu path của SVG — dữ liệu đó
là tuyệt đối.

**Mảng gradient không được gắn nhãn.** Không gì trong `values/gradient` nói
các stop màu kết thúc ở đâu và các stop độ trong suốt bắt đầu ở đâu. Con số đó
đến từ `properties/gradient-property.p` ("Color stop count") — một trường cùng
cấp, không nằm trong mảng. [confirmed] Bộ đọc nào bỏ qua `p` thì không thể
phân tích đúng một gradient có stop trong suốt.

---

## 5. Layers

### 5.1 Base dùng chung

`layers/layer` — bắt buộc `ty`, `ip`, `op`. [confirmed]

| Khóa | Loại | Ý nghĩa |
|---|---|---|
| `ty` | integer | Kiểu layer (trường phân biệt) |
| `nm`, `mn` | string | Tên, match name (từ `helpers/visual-object`) |
| `ind` | integer | Chỉ số, dùng cho parenting và cho expression |
| `parent` | integer | `ind` của layer cha |
| `ip` | number | In point — frame mà layer bắt đầu hiện |
| `op` | number | Out point — frame mà layer thôi hiện |
| `st` | number | Start time, mặc định 0 |
| `sr` | number | Time stretch, mặc định 1 |
| `ddd` | int-boolean | Layer có phải 3D hay không, mặc định 0 |
| `hd` | boolean | Ẩn |

`layers/visual-layer` thêm mọi thứ liên quan đến vẻ ngoài. Bắt buộc `ks`.
[confirmed]

| Khóa | Loại | Ý nghĩa |
|---|---|---|
| `ks` | `helpers/transform` | Transform của layer |
| `ao` | int-boolean | Auto-orient: tự xoay theo đường chuyển động, mặc định 0 |
| `tt` | `constants/matte-mode` | Track matte mode |
| `tp` | integer | Chỉ số layer matte cha; "if omitted assume the layer above the current one" |
| `td` | int-boolean | Đặt 1 ở layer *được dùng làm* matte |
| `hasMask` | boolean | Layer có mask hay không |
| `masksProperties` | mảng `helpers/mask` | Các mask |
| `ef` | mảng `effects/all-effects` | Các layer effect |
| `sy` | mảng `styles/all-layer-styles` | Các layer style |
| `bm` | `constants/blend-mode` | Blend mode, mặc định 0 |
| `mb` | boolean | Motion blur được bật |
| `ct` | int-boolean | Collapse transform — "Marks that transforms should be applied before masks", mặc định 0 |
| `cp` | boolean | **Đã bỏ (deprecated)**, thay bằng `ct` |
| `cl`, `ln`, `tg` | string | CSS class, XML `id`, tên thẻ XML — gợi ý cho renderer chạy trên SVG |

Việc có `cl` / `ln` / `tg` là chi tiết nhỏ nhưng đáng chú ý: Lottie lường
trước rằng một số player sẽ render bằng DOM SVG, và cho phép tác giả tự đặt
tên các phần tử. [confirmed]

### 5.2 Các kiểu layer cụ thể

| `ty` | Định nghĩa | Bắt buộc ngoài base | Mục đích |
|---:|---|---|---|
| 0 | `precomposition-layer` | `refId` | vẽ một asset precomposition; cũng có `w`, `h` (clip rect), `st`, `tm` (time remap) |
| 1 | `solid-layer` | `sw`, `sh`, `sc` | một hình chữ nhật màu đặc; `sc` là chuỗi `#RRGGBB` |
| 2 | `image-layer` | `refId` | vẽ một asset ảnh |
| 3 | `null-layer` | — | không có nội dung; chỉ để làm layer cha |
| 4 | `shape-layer` | `shapes` | nội dung vector |
| 5 | `text-layer` | `t` | text, xem § 7.3 |
| 6 | `audio-layer` | `au` | âm thanh; mở rộng `layer`, không phải `visual-layer` |
| 13 | `camera-layer` | `ks`, `pe` | camera 3D; mở rộng `layer` và thêm `ks` và `pe` (perspective) riêng của nó |
| 15 | `data-layer` | — | tham chiếu một asset data source qua `refId` |

[confirmed] Chú ý các khoảng trống trong dãy số, và chú ý `camera-layer` cùng
`audio-layer` **không phải** visual layer — chúng mở rộng thẳng `layers/layer`,
nên không có mask, effect hay blend mode.

Với một bộ xuất frame, chỉ các kiểu 0, 1, 2, 3, 4, 5 mới tạo ra được pixel.
[inferred]

### 5.3 Parenting

Parenting đi theo `ind`, không theo lồng nhau: `parent` của một layer giữ
`ind` của một layer khác trong **cùng** composition. [confirmed] Vì vậy mảng
layer là một danh sách phẳng, còn quan hệ transform là một đồ thị phủ lên trên
nó. Hai hệ quả:

- Thứ tự vẽ và thứ tự transform độc lập với nhau. Một layer con có thể nằm rất
  xa layer cha trong danh sách.
- Mỗi precomposition là một không gian tên `ind` riêng. Một layer không thể
  parent vào một layer nằm trong precomp. [inferred từ mô tả của `parent`,
  "Must be the `ind` property of another layer", kết hợp với precomps là các
  composition riêng]

### 5.4 Masks và mattes

Lottie có **hai** cơ chế che khuất không liên quan gì nhau, và một file có thể
dùng cả hai trên cùng một layer.

**Mask** (`masksProperties`) là các shape gắn theo từng layer. `helpers/mask`
yêu cầu `pt`: [confirmed]

| Khóa | Ý nghĩa |
|---|---|
| `pt` | Hình dạng mask, một `bezier-property` |
| `mode` | `constants/mask-mode`, mặc định `"i"` |
| `o` | Opacity 0..100, mặc định 100 |
| `x` | Expand |
| `inv` | Đảo ngược mask, mặc định false |

Mask mode là các ký tự đơn: `"n"` none, `"a"` add, `"s"` subtract, `"i"`
intersect, `"l"` lighten, `"d"` darken, `"f"` difference. [confirmed] Schema mô
tả mode là cách một mask "interacts (blends) with the **preceding masks in the
stack**", nghĩa là danh sách mask được xử lý theo thứ tự, mỗi cái ghép vào kết
quả tích lũy trước đó.

**Track mattes** (`tt` / `tp` / `td`) dùng một *layer* để mask một layer khác.
`constants/matte-mode`: 0 normal, 1 alpha, 2 inverted alpha, 3 luma, 4
inverted luma. [confirmed] Layer làm nguồn matte mang `td: 1`; layer bị mask mang `tt`, còn
`tp` chỉ ra layer nguồn bằng chỉ số — nếu thiếu `tp` thì mặc định là "layer
ngay phía trên layer hiện tại".

Về mặt cấu trúc, chỗ này giống cơ chế masking hai trường của Moho (`group_mask`
trên container, cộng `masking` trên từng layer con) mô tả trong
[`moho-project-file-format.md`](moho-project-file-format.md) § 10 — cũng là
hai trường độc lập phải đọc cùng nhau. Nhưng cơ chế thì không tương đương:
mask của Lottie là danh sách shape gắn theo layer, còn của Moho là một cờ đánh
dấu vai trò đặt trên layer anh em.

---

## 6. Các phần tử shape

Mảng `shapes` của một shape layer chứa `shapes/all-graphic-elements` — một
`oneOf` trên 19 kiểu cụ thể cộng nhánh dự phòng unknown. Tất cả đều mở rộng
`shapes/graphic-element`, nơi cung cấp `ty`, `nm`, `mn`, `hd`, `bm`, `ix`,
`cl`, `ln`. [confirmed]

### 6.1 Bảng đầy đủ các phần tử

| `ty` | Định nghĩa | Nhóm | Trường riêng bắt buộc |
|---|---|---|---|
| `gr` | `group` | container | — (`it` giữ các con, `np`/`cix` là các chỉ số) |
| `sh` | `path` | geometry | `ks` (một `bezier-property`) |
| `rc` | `rectangle` | geometry | `s` (kích thước), `p` (tâm); `r` = bán kính bo góc |
| `el` | `ellipse` | geometry | `s`, `p` |
| `sr` | `polystar` | geometry | `or`, `os`, `pt`, `p`, `r`; `sy` star/polygon, `ir`, `is` |
| `fl` | `fill` | style | `c` (màu); `r` = fill rule |
| `st` | `stroke` | style | `c`; cộng toàn bộ `base-stroke` |
| `gf` | `gradient-fill` | style | toàn bộ `base-gradient`; `r` = fill rule |
| `gs` | `gradient-stroke` | style | `base-stroke` + `base-gradient` |
| `no` | `no-style` | style | — ("a style for shapes without fill or stroke") |
| `tr` | `transform` | transform | toàn bộ `helpers/transform` |
| `tm` | `trim-path` | modifier | `o`, `s`, `e`; `m` = song song hoặc tuần tự |
| `rp` | `repeater` | modifier | `c` (số bản sao), `tr` (một `repeater-transform`); `o`, `m` |
| `rd` | `rounded-corners` | modifier | `r` (bán kính) |
| `mm` | `merge` | modifier | `mm` = merge mode |
| `op` | `offset-path` | modifier | `a` (mức offset), `lj`, `ml` |
| `pb` | `pucker-bloat` | modifier | `a` (mức áp dụng, tính theo phần trăm) |
| `tw` | `twist` | modifier | `a` (góc), `c` (tâm) |
| `zz` | `zig-zag` | modifier | `r` (tần số), `s` (biên độ), `pt` (loại điểm) |

[confirmed]

### 6.2 Ba base trung gian

- `shapes/shape` — base hình học. Chỉ thêm `d`, một `constants/shape-direction`
  (1 normal, 3 reversed), "mostly relevant when using trim path". Được mở rộng
  bởi `path`, `rectangle`, `ellipse`, `polystar`.
- `shapes/shape-style` — base style. Thêm `o`, opacity, bắt buộc. Được mở rộng
  bởi `fill`, `stroke`, `gradient-fill`, `gradient-stroke`, `no-style`.
- `shapes/modifier` — base cho modifier. Không thêm trường nào; nó tồn tại chỉ
  để nói lên ý định: "Modifiers change the bezier curves of neighbouring
  shapes."

[confirmed]

### 6.3 Chi tiết stroke và gradient

`shapes/base-stroke` yêu cầu `w`: [confirmed]

| Khóa | Ý nghĩa |
|---|---|
| `w` | Độ rộng nét (một scalar property) |
| `lc` | Line cap, mặc định 2 — 1 butt, 2 round, 3 square |
| `lj` | Line join, mặc định 2 — 1 miter, 2 round, 3 bevel |
| `ml` | Miter limit, một số thường, mặc định 0 |
| `ml2` | Miter limit, "animatable alternative to `ml`" |
| `d` | Mảng `shapes/stroke-dash` |

Mỗi mục dash có `n` — một `stroke-dash-type` nhận `"d"` dash, `"g"` gap hoặc
`"o"` offset — và `v` là độ dài. [confirmed] Nghĩa là `stroke-dasharray` và
`stroke-dashoffset` của SVG ở đây được mã hóa thành một danh sách có gắn nhãn,
chứ không phải hai trường riêng.

`shapes/base-gradient` yêu cầu `s`, `e`, `g`, `t`: [confirmed] điểm bắt đầu,
điểm kết thúc, màu, và `constants/gradient-type` (1 linear, 2 radial,
3 conic). `h` (highlight length, một phần trăm giữa `s` và `e`) và `a`
(highlight angle) tồn tại cho các gradient radial.

### 6.4 Quy tắc thứ tự

Danh sách shape của Lottie không phải một danh sách vẽ thông thường. Phần tử
style áp dụng cho "neighbouring shapes", còn modifier thì thay đổi "the bezier
curves of neighbouring shapes" — cả hai cụm này đều lấy từ mô tả trong schema.
[confirmed] Schema **không** định nghĩa chính xác "neighbouring" là gì, cũng
không nói style áp dụng cho phần tử đứng trước hay đứng sau nó trong mảng. Quy
tắc đó nằm ở player và ở tài liệu dạng văn bản, không nằm trong schema máy đọc
được. [confirmed — vì schema không nói gì]

Đây là khoảng trống thật với bất kỳ ai viết bộ **ghi** Lottie: tạo ra một mảng
có thứ tự đúng như player mong đợi thì không thể kiểm chứng chỉ bằng schema.
Phải kiểm bằng một renderer thật.

---

## 7. Assets, text, effects, styles, slots

### 7.1 Assets

`assets/asset` yêu cầu `id`, một "unique identifier used by layers when
referencing this asset". `assets/file-asset` thêm `p` (tên file hoặc data
URL), `u` (đường dẫn), và `e` (nhúng — "If `1`, `p` is a Data URL").
[confirmed]

| Định nghĩa | Mở rộng | Thêm |
|---|---|---|
| `precomposition` | `asset` + `composition/composition` | `fr` (framerate riêng), `xt` (extra composition flag) |
| `image` | `file-asset` + `slottable-object` | `w`, `h`, `t` (const `"seq"` đánh dấu một image sequence) |
| `sound` | `file-asset` | — |
| `data-source` | `file-asset` | `t` const 3 |

[confirmed] Vậy một precomposition *vừa* là asset *vừa* là composition: nó có
`id` riêng và mảng `layers` riêng. Đó chính là cách Lottie lồng nhau.

### 7.2 Effects và layer styles

Hai hệ thống tách biệt, cả hai trên `visual-layer`.

**Effects** (`ef`) mô phỏng theo các effect của After Effects. 16 kiểu cụ thể
cộng một base và một union "all". [confirmed] Các giá trị `ty`: 20 tint, 21 fill,
22 stroke, 23 tritone, 24 pro levels, 25 drop shadow, 26 radial wipe, 27
displacement map, 28 set matte, 29 gaussian blur, 30 twirl, 31 mesh warp, 32
wavy, 33 spherize, 34 puppet. Còn có `custom-effect` với `ty` 5, được mô tả là
"Some lottie files use `ty` = 5 for many different effects" — một lời thừa nhận
thẳng thắn rằng trường này phân biệt không đáng tin. [confirmed]

Tham số của effect là `effect-values/*`, cũng phân biệt bằng `ty`: 0 slider, 1
angle, 2 colour, 3 point, 4 checkbox, 6 ignored, 7 drop-down, 10 layer.
[confirmed]

**Layer styles** (`sy`) mô phỏng theo các layer style của Photoshop: `ty` 0 stroke,
1 drop shadow, 2 inner shadow, 3 outer glow, 4 inner glow, 5 bevel emboss, 6
satin, 7 colour overlay, 8 gradient overlay. [confirmed]

Phần lớn player chỉ hỗ trợ một ít trong số đó. Player nào hỗ trợ cái nào là
câu hỏi tùy từng player, không phải câu hỏi về schema.

### 7.3 Text

14 định nghĩa. Lõi là `text/text-data`, tới được từ `layers/text-layer.t`, giữ
text document (`animated-text-document`, có các keyframe là
`text-document-keyframe`), danh sách font, các range (`text-range` với
`text-range-selector` và `text-style`), các tùy chọn căn lề, và follow-path.

Gốc tài liệu cũng có thể mang `chars` — một mảng `text/character-data` định
nghĩa đường viền glyph dưới dạng shape Lottie (`character-shapes`) hoặc dưới
dạng precomp (`character-precomp`). Mô tả ở gốc nói rõ hệ quả: "If present a
player might only render characters defined here and nothing else."
[confirmed]

Đó là cách thực tế để có text mà không cần font: exporter chuyển glyph thành
đường viền ngay từ đầu. [inferred]

### 7.4 Slots

`helpers/slot` là một đối tượng với một `p` bắt buộc, "Property Value".
`helpers/slottable-object` thêm `sid`, "Identifier to look up the slot".
Trường `sid` riêng của property base được mô tả là "One of the ID in the
file's slots". [confirmed]

Slot là cơ chế theming của Lottie: một property khai "giá trị của tôi lấy từ
slot X", rồi phía host đổi X lúc chạy mà không phải sửa cây layer. ThorVG mở
thẳng cơ chế này ra (§ 10.3).

---

## 8. Mô hình thời gian

Mục này quan trọng nhất với tính năng xuất frame, nên mỗi ý đều nêu kèm bằng
chứng.

### 8.1 Frame, không phải giây

Mọi giá trị thời gian trong Lottie là một **số frame**. `properties/base-keyframe.t`
có tiêu đề "Time" và được mô tả là "Frame number". `ip`/`op`/`st` của layer
cũng là số frame. Chỉ `fr` mới quy được ra thời gian thực. [confirmed]

```
time_in_seconds = frame / fr
```

### 8.2 Frame là số thực, không phải số nguyên

`fr`, `ip`, `op`, `st`, `sr`, và `t` của keyframe đều được khai báo `"type":
"number"`, không phải `"integer"`. Chỉ `w`, `h`, `ind`, `parent`, và `ver` là
các số nguyên. [confirmed]

Vậy **"frame 12.5" là một yêu cầu hợp lệ và có ý nghĩa.** Bộ xuất frame nên
nhận số thực, không phải số nguyên. Điều này cũng có nghĩa `op - ip` là số
frame, và không nhất thiết phải là số nguyên.

### 8.3 Thời gian theo layer

Ba trường sau dịch và co giãn dòng thời gian riêng của một layer so với dòng
thời gian của composition:

| Trường | Tiêu đề trong schema | Mặc định |
|---|---|---|
| `ip` | In Point — "Frame when the layer becomes visible" | bắt buộc |
| `op` | Out Point — "Frame when the layer becomes invisible" | bắt buộc |
| `st` | Start Time | 0 |
| `sr` | Time Stretch | 1 |

[confirmed] Schema có đặt tiêu đề cho `st` và `sr` nhưng **không có dòng mô tả
nào**, nên thứ tự kết hợp chính xác của chúng là không được schema định nghĩa.
Cách hiểu thông thường: thời gian cục bộ của một layer là
`(composition_frame - st) / sr`, còn `ip`/`op` thì so theo thời gian của
composition. [inferred — schema *không* xác nhận điều này, nên cần kiểm chứng
với một renderer trước khi dựa vào]

`precomposition-layer` còn có `tm` (Time Remap), mô tả là "Timeline remap
function (frame index -> time in seconds)". [confirmed] Chú ý chỗ đổi đơn vị:
đầu ra của remap là **giây**, trong khi mọi thứ khác đều là frame. Nếu mô tả
đó chính xác thì muốn tính một precomp có time remap, phải nhân lại với `fr`
của chính precomp đó. Chỗ này nên kiểm chứng với một player trước khi cài đặt.
[đã đánh dấu là chưa chắc chắn]

Mỗi asset precomposition mang `fr` **riêng**. [confirmed] Nên một composition
lồng bên trong có thể chạy ở framerate khác với composition cha.

### 8.4 Markers

`helpers/marker` có `cm` (comment), `tm` (thời gian), `dr` (duration), và mô
tả của module là "Defines named portions of the composition". [confirmed]
Marker đặt tên cho từng dải frame. ThorVG có thể chọn một marker và chỉ phát
đúng dải đó (§ 10.3).

### 8.5 Vậy "xuất frame N" thực chất là làm gì

Từ những điều trên, muốn tính một tài liệu Lottie tại frame `N` thì với mỗi
layer phải làm lần lượt: [inferred, ghép lại từ các ngữ nghĩa trường đã xác
nhận]

1. Bỏ qua layer nếu `N < ip` hoặc `N >= op`, hoặc nếu `hd` bằng true.
2. Quy `N` về thời gian cục bộ của layer bằng `st` và `sr`.
3. Tính mọi property có hoạt ảnh tại thời gian cục bộ đó: tìm hai keyframe bao
   quanh rồi áp dụng easing `h` / `i` / `o`.
4. Ghép chuỗi transform bằng cách lần theo `parent` về tới gốc.
5. Với layer precomp thì đệ quy, dùng `fr` và `tm` riêng của precomp.

Không bước nào trong danh sách này cần tới rasteriser. Chính nhận xét đó làm
cho phương án "tự viết bộ tính toán" ở § 13 trở nên khả thi.

---

## 9. ThorVG là gì

### 9.1 ThorVG là gì

ThorVG (Thor Vector Graphics) là một engine đồ họa vector mã nguồn mở.
[reported, `thorvg.org`]

| Thuộc tính | Giá trị | Bằng chứng |
|---|---|---|
| Ngôn ngữ | lõi C++, với các API C++, C và JavaScript | [reported] |
| Giấy phép | MIT | [reported] |
| Xuất xứ | do Hermet Park tạo ra năm 2020 | [reported] |
| Bản mới nhất lúc viết tài liệu | `v1.1.0`, phát hành 2026-07-22 | [confirmed] qua GitHub releases API |
| Kích thước lõi | khoảng 170 KB | [reported] |
| Các bên đang dùng, nêu trên trang chủ | Canva, Godot, LVGL | [reported] |

### 9.2 Đọc được gì, ghi được gì

Lấy từ `meson_options.txt` trong repo ThorVG — đây là danh sách module của
chính bản build, nên là căn cứ về khả năng thật, không phải lời quảng cáo.
[confirmed]

```
loaders : '', svg, png, jpg, lottie, ttf, otf, webp, media, all
          (default: svg, lottie, ttf)
savers  : '', gif, all
          (default: '')
engines : cpu, gl, wg, all          (default: cpu)
bindings: '', capi                  (default: '')
tools   : '', svg2png, lottie2gif, all   (default: '')
extra   : '', opengl_es, lottie_exp, openmp   (default: lottie_exp, openmp)
```

Từ đó rút ra ba điều, và cả ba đều quan trọng với repo này.

**Saver duy nhất của ThorVG là GIF.** Có đúng một thư mục dưới `src/savers`,
và nó là `gif`. [confirmed] ThorVG có thể đọc SVG nhưng **không thể ghi SVG**,
nên nó sẽ không bao giờ đưa cho bạn một file vector. Nhưng nó vẫn đưa được
*dữ liệu* vector qua API đọc scene — xem § 10.5, chính điều đó làm Phương án D
ở § 13.4 trở nên khả thi.

**API C phải bật thủ công (opt-in).** `bindings` mặc định để rỗng. Một bản
build tiêu chuẩn sẽ không có hàm C `libthorvg` nào, trừ khi được cấu hình với
`-Dbindings=capi`. [confirmed]

**Expression của Lottie thì bật sẵn.** `extra` mặc định đã bao gồm
`lottie_exp`. [confirmed]

### 9.3 Các backend render

`engines` cho chọn `cpu`, `gl` và `wg`. API C có một hàm tạo canvas riêng cho
mỗi backend: [confirmed, từ `thorvg_capi.h`]

```c
TVG_API Tvg_Canvas tvg_swcanvas_create(Tvg_Engine_Option op);
TVG_API Tvg_Canvas tvg_glcanvas_create(Tvg_Engine_Option op);
TVG_API Tvg_Canvas tvg_wgcanvas_create(Tvg_Engine_Option op);
```

Chỉ canvas phần mềm mới render được thẳng vào một vùng nhớ thường, không cần
hệ thống cửa sổ:

```c
TVG_API Tvg_Result tvg_swcanvas_set_target(Tvg_Canvas canvas, uint32_t* buffer,
        uint32_t stride, uint32_t w, uint32_t h, Tvg_Colorspace cs);
```

[confirmed] Theo chính ghi chú trong header, lời gọi đó chỉ nhận các không
gian màu `TVG_COLORSPACE_ABGR8888`, `ARGB8888`, `ABGR8888S` và `ARGB8888S`,
trong đó hậu tố `S` nghĩa là alpha **chưa nhân trước (un-premultiplied)**, còn
tên không có `S` nghĩa là **alpha đã nhân trước (premultiplied)**. [confirmed]
Chọn sai chỗ này sẽ tạo ra viền sai rất khó phát hiện trên artwork trong suốt,
nên cần nói rõ.

Để xuất một frame offline, không giao diện, canvas phần mềm là lựa chọn hợp lý
duy nhất. [inferred]

### 9.4 Các công cụ đi kèm

`tools/` chứa đúng hai chương trình. [confirmed]

**`tvg-svg2png`** — nguyên văn dòng usage của nó:

```
tvg-svg2png [SVG file] or [SVG folder] [-r resolution] [-b bgColor]
```

Nó kiểm tra đầu vào bằng cách so đúng phần mở rộng `.svg`, và loại mọi thứ
khác. Nó không có cờ chọn frame. [confirmed, từ
`tools/svg2png/svg2png.cpp`]

**`tvg-lottie2gif`** — nguyên văn dòng usage của nó:

```
tvg-lottie2gif [Lottie file] or [Lottie folder] [-r resolution] [-f fps] [-b background color]
```

Nó kiểm tra đầu vào bằng cách so đúng phần mở rộng `.json`, và toàn bộ phần
thân chuyển đổi chỉ gồm: tạo một `Animation`, nạp file vào
`animation->picture()`, co giãn, rồi `saver->save(animation, out, 100, fps)`.
Nó cũng không có cờ chọn frame. [confirmed, từ
`tools/lottie2gif/lottie2gif.cpp`]

**Cả hai công cụ đi kèm đều không xuất được một frame đơn lẻ.** Đó là giới hạn
đã được xác nhận, không phải ý kiến chủ quan.

---

## 10. API Lottie của ThorVG

Mọi chữ ký hàm dưới đây được trích nguyên văn từ
`src/bindings/capi/thorvg_capi.h` ở nhánh `main`. [confirmed]

### 10.1 Đối tượng animation

```c
TVG_API Tvg_Animation tvg_animation_new(void);
TVG_API Tvg_Paint     tvg_animation_get_picture(Tvg_Animation animation);
TVG_API Tvg_Result    tvg_animation_set_frame(Tvg_Animation animation, float no);
TVG_API Tvg_Result    tvg_animation_get_frame(Tvg_Animation animation, float* no);
TVG_API Tvg_Result    tvg_animation_get_total_frame(Tvg_Animation animation, float* cnt);
TVG_API Tvg_Result    tvg_animation_get_duration(Tvg_Animation animation, float* duration);
TVG_API Tvg_Result    tvg_animation_set_segment(Tvg_Animation animation, float begin, float end);
TVG_API Tvg_Result    tvg_animation_get_segment(Tvg_Animation animation, float* begin, float* end);
TVG_API Tvg_Result    tvg_animation_del(Tvg_Animation animation);
```

Tham số frame là `float`, khớp với mô hình frame số thực của chính Lottie
(§ 8.2). Tài liệu trong header nêu thêm bốn ràng buộc mà bên gọi phải tuân
thủ: [confirmed]

- `no` "should be less than the `tvg_animation_get_total_frame()`"; frame được
  đánh số "starts from 0", và frame hiện tại nằm "between 0 and
  totalFrame() - 1".
- Nếu frame mới lệch so với frame hiện tại **dưới 0.001** thì lời gọi bị bỏ
  qua và trả về `TVG_RESULT_INSUFFICIENT_CONDITION`. Header ghi rõ đây là cách
  tối ưu hiệu năng. Nghĩa là bên gọi không được coi `INSUFFICIENT_CONDITION`
  là lỗi — đó là kết quả bình thường khi bạn đặt lại đúng frame đang hiển thị.
- `tvg_animation_get_total_frame` trả về 0 "if the Picture is not properly
  configured", nên 0 vừa là dấu hiệu lỗi vừa là kết quả rỗng hợp lệ.
- Picture do `tvg_animation_get_picture` trả về "is owned by Animation. It
  should not be deleted manually."

`tvg_animation_set_segment` (có từ 1.0) giới hạn phát lại trong một dải frame,
sau đó "the number of animation frames and the playback time are calculated by
mapping the playback segment as the entire range" — tức là nó **đánh số lại**
frame, nên đặt segment sẽ làm đổi ý nghĩa của `set_frame(N)`. [confirmed]

### 10.2 Nạp file

Không có lời gọi loader riêng cho Lottie. File Lottie được nạp qua giao diện
picture dùng chung: [confirmed]

```c
TVG_API Tvg_Result tvg_picture_load(Tvg_Paint picture, const char* path);
TVG_API Tvg_Result tvg_picture_load_data(Tvg_Paint picture, const char* data, uint32_t size,
                                         const char* mimetype, const char* rpath, bool copy);
```

Định dạng được nhận biết qua phần mở rộng hoặc MIME type. Ví dụ của chính
ThorVG chấp nhận hai phần mở rộng Lottie:

```cpp
//ignore if not lottie.
const char *ext = path + strlen(path) - 4;
if (strcmp(ext, "json") && strcmp(ext, "lot")) return;
```

[confirmed, từ `thorvg.example/src/Lottie.cpp`] Vậy cả `.json` lẫn `.lot` đều
được nhận.

`tvg_picture_load_data` rất quan trọng nếu tích hợp bằng Python: nó nhận một
vùng nhớ, kèm `rpath` (thư mục gốc để phân giải các tham chiếu ngoài của
file), nên có thể render một tài liệu Lottie mà không cần ghi gì ra đĩa.
[confirmed]

### 10.3 Các lời gọi dành riêng cho Lottie

```c
TVG_API Tvg_Animation tvg_lottie_animation_new(void);
TVG_API uint32_t   tvg_lottie_animation_gen_slot(Tvg_Animation animation, const char* slot);
TVG_API Tvg_Result tvg_lottie_animation_apply_slot(Tvg_Animation animation, uint32_t id);
TVG_API Tvg_Result tvg_lottie_animation_del_slot(Tvg_Animation animation, uint32_t id);
TVG_API Tvg_Result tvg_lottie_animation_set_marker(Tvg_Animation animation, const char* marker);
TVG_API Tvg_Result tvg_lottie_animation_get_markers_cnt(Tvg_Animation animation, uint32_t* cnt);
TVG_API Tvg_Result tvg_lottie_animation_get_marker_info(Tvg_Animation animation, uint32_t idx,
                                                        const char** name, float* begin, float* end);
TVG_API Tvg_Result tvg_lottie_animation_tween(Tvg_Animation animation, float from, float to, float progress);
TVG_API Tvg_Result tvg_lottie_animation_tween_to(Tvg_Animation animation, float to);
TVG_API Tvg_Result tvg_lottie_animation_tween_go(Tvg_Animation animation, float progress);
TVG_API Tvg_Result tvg_lottie_animation_set_quality(Tvg_Animation animation, uint8_t value);
TVG_API Tvg_Result tvg_lottie_animation_set_audio_resolver(Tvg_Animation animation, Tvg_Audio_Resolver resolver, void* data);
```

[confirmed] Chúng ánh xạ một-một sang các khái niệm Lottie đã nói ở trên: slot
(§ 7.4) và marker (§ 8.4). Nhóm `tween*` trộn giữa hai frame — đây là tính
năng riêng của ThorVG, không phải của Lottie.

Chú ý `tvg_lottie_animation_new` trả về cùng kiểu handle `Tvg_Animation` như
`tvg_animation_new`, nên các lời gọi frame chung ở § 10.1 dùng được nguyên vẹn
cho nó. [confirmed]

### 10.4 Canvas và saver

```c
TVG_API Tvg_Result tvg_engine_init(unsigned threads);
TVG_API Tvg_Result tvg_engine_term(void);
TVG_API Tvg_Result tvg_canvas_add(Tvg_Canvas canvas, Tvg_Paint paint);
TVG_API Tvg_Result tvg_canvas_update(Tvg_Canvas canvas);
TVG_API Tvg_Result tvg_canvas_draw(Tvg_Canvas canvas, bool clear);
TVG_API Tvg_Result tvg_canvas_sync(Tvg_Canvas canvas);
TVG_API Tvg_Result tvg_saver_save_animation(Tvg_Saver saver, Tvg_Animation animation,
                                            const char* path, uint32_t quality, uint32_t fps);
```

[confirmed] Bắt buộc gọi `tvg_canvas_sync` trước khi đọc vùng nhớ đích, vì
việc vẽ có thể chạy bất đồng bộ nếu engine được khởi tạo với nhiều thread.
Saver cũng bất đồng bộ, và header ghi "To guarantee the saving is done, call
`tvg_saver_sync()` afterwards."

`tvg_saver_save_animation` ghi trọn một animation, mà `savers` chỉ có `gif`,
nên định dạng đầu ra duy nhất nó tạo ra được là GIF. [confirmed cho danh sách
saver; inferred cho kết luận]

### 10.5 Đọc lại scene

ThorVG không *ghi* được SVG, nhưng có thể *hỏi nó vừa vẽ những gì*. Điều này
làm thay đổi đáng kể các phương án ở § 13, nên phần bằng chứng được trình bày
đầy đủ.

**Duyệt cây.** Module Accessor — "a module for manipulation of the scene
tree": [confirmed]

```c
TVG_API Tvg_Accessor tvg_accessor_new(void);
TVG_API Tvg_Result tvg_accessor_set(Tvg_Accessor accessor, Tvg_Paint paint,
                                    bool (*func)(Tvg_Paint paint, void* data), void* data);
TVG_API Tvg_Result tvg_accessor_del(Tvg_Accessor accessor);
```

Tài liệu của nó: "Iterates through all descendents of the scene passed
through the paint argument while calling func on each... When func returns
false iteration stops." [confirmed]

**Nhận biết từng node.** `tvg_paint_get_type` trả về một `Tvg_Type`:
`TVG_TYPE_SHAPE`, `TVG_TYPE_SCENE`, `TVG_TYPE_PICTURE`, `TVG_TYPE_TEXT`, cộng
`TVG_TYPE_LINEAR_GRAD` (10) và `TVG_TYPE_RADIAL_GRAD` (11). [confirmed]

**Đọc hình học.** [confirmed]

```c
TVG_API Tvg_Result tvg_shape_get_path(const Tvg_Paint paint,
        const Tvg_Path_Command** cmds, uint32_t* cmdsCnt,
        const Tvg_Point** pts, uint32_t* ptsCnt);
```

Và `Tvg_Path_Command` là một `uint8_t` gồm bốn giá trị, tài liệu nêu rõ cách
ánh xạ: [confirmed]

| Giá trị | Hằng số | Nguyên văn trong header |
|---:|---|---|
| 0 | `TVG_PATH_COMMAND_CLOSE` | "corresponds to Z command in the svg path commands" |
| 1 | `TVG_PATH_COMMAND_MOVE_TO` | "corresponds to M command in the svg path commands" |
| 2 | `TVG_PATH_COMMAND_LINE_TO` | "corresponds to L command in the svg path commands" |
| 3 | `TVG_PATH_COMMAND_CUBIC_TO` | "corresponds to C command in the svg path commands" |

**Mô hình path bên trong ThorVG chính là mô hình path của SVG.** Đây không
phải suy luận; header nói thẳng điều đó bốn lần.

**Đọc thuộc tính hiển thị.** [confirmed]

```c
tvg_paint_get_transform(paint, &matrix)       tvg_paint_get_opacity(paint, &opacity)
tvg_paint_get_visible(paint)                  tvg_paint_get_parent(paint)
tvg_paint_get_clip(paint)                     tvg_paint_get_mask_method(paint, target, &method)
tvg_shape_get_fill_color(...)                 tvg_shape_get_fill_rule(paint, &rule)
tvg_shape_get_stroke_color(...)               tvg_shape_get_stroke_width(paint, &width)
tvg_shape_get_stroke_cap(paint, &cap)         tvg_shape_get_stroke_join(paint, &join)
tvg_shape_get_stroke_dash(paint, &pattern, &cnt, &offset)
tvg_shape_get_stroke_miterlimit(paint, &limit)
tvg_shape_get_gradient(paint, &grad)          tvg_shape_get_stroke_gradient(paint, &grad)
tvg_linear_gradient_get(grad, &x1, &y1, &x2, &y2)
tvg_radial_gradient_get(grad, &cx, &cy, &r, &fx, &fy, &fr)
tvg_gradient_get_color_stops(grad, &stops, &cnt)
tvg_gradient_get_spread(grad, &spread)        tvg_gradient_get_transform(grad, &m)
```

Tập hàm đó về cơ bản bao phủ mọi thuộc tính mà một `<path>` SVG cần.
[confirmed rằng các hàm này tồn tại; còn đánh giá "đủ dùng" thì là inferred]

**Những thứ không đọc được theo cách này.** Không có hàm đọc đường viền glyph
trên một paint `TVG_TYPE_TEXT`, và các effect raster như blur hay drop shadow
thì không có dạng vector tương đương để đọc. Còn những gì ThorVG đã bake sẵn
vào dữ liệu path — trim path, repeater, offset path, merge — thì trả về cũng
đã bake sẵn, mà thường đó lại đúng ý một bộ ghi SVG. [inferred]

**Chưa kiểm chứng.** Chưa có dòng code nào trong repo này duyệt qua một scene
ThorVG. Cụ thể, chưa kiểm tra xem một `Picture` nạp từ Lottie có để lộ các
node con cho Accessor hay không, và hình học đọc về là tọa độ cục bộ hay tọa
độ đã gộp. Hàm `tvg_picture_get_paint(picture, id)` có tồn tại, gợi ý rằng
phần bên trong picture là chạm tới được, nhưng đó mới là gợi ý, chưa phải bằng
chứng. Đây là thứ đáng kiểm tra đầu tiên nhất.

---

## 11. Lottie và ThorVG liên hệ thế nào

### 11.1 Hai nhánh tài liệu

Có hai nhánh tài liệu Lottie khác nhau, và rất dễ nhầm lẫn vì cả hai đều phát
hành một JSON Schema:

| | lottie-docs | lottie-spec |
|---|---|---|
| URL | `lottiefiles.github.io/lottie-docs` | `lottie.github.io/lottie-spec` |
| Người duy trì | LottieFiles (Design Barn Inc.) [reported] | Lottie Animation Community [reported] |
| Trạng thái tự công bố | tài liệu định dạng đầy đủ | "a work in progress", bao phủ "a subset of features that have been approved by the Lottie Animation Community" [reported] |
| Có bản sao trong repo này | **có** — `lottie/lottie.schema.json`, `$id` xác nhận | không |

[confirmed cho `$id`; reported cho phần còn lại]

Khác biệt thực tế: **lottie-docs mang tính mô tả, còn lottie-spec là chuẩn
đang xây dựng.** lottie-docs ghi lại những gì file ngoài thực tế đang chứa, kể
cả các trường đã bỏ (`e` trên keyframe), các đặc thù riêng của từng nơi
(`custom-effect` với `ty` 5 "used for many different effects"), và cả layer
style kiểu Photoshop. lottie-spec thì nhắm tới việc chuẩn hóa một tập con.

Để *đọc* file Lottie, schema mang tính mô tả trong repo này là cái hữu ích hơn,
vì nó bao phủ được nhiều thứ mà file thật hay chứa. Để *ghi* file Lottie thì
nhắm vào tập con đã được duyệt sẽ an toàn hơn. [inferred]

### 11.2 Định dạng, các player, và chỗ đứng của ThorVG

Lottie là định dạng không có bản cài đặt tham chiếu nào được công nhận là
renderer "chính thức". Có vài player độc lập — lottie-web (player chạy trên
trình duyệt, ra đời cùng Bodymovin), rlottie, Skottie (nằm trong Skia), và
ThorVG. Mỗi player hỗ trợ một tập con riêng. [inferred; tài liệu này không rà
soát các player khác]

Hệ quả của việc đó là điều quan trọng nhất cần hiểu về hệ sinh thái Lottie:
**"Lottie hợp lệ" và "render đúng trên player X" là hai câu hỏi khác nhau.**
Schema trả lời câu thứ nhất. Chỉ có chạy player thật mới trả lời được câu thứ
hai. Repo này đang có schema, nên trả lời được câu thứ nhất ngay hôm nay; câu
thứ hai thì phải build hoặc cài thêm thứ gì đó.

Chỗ đứng của ThorVG, theo chính tài liệu của nó, là "Lottie is a first-class
citizen in ThorVG" với "extensive support for the Lottie specification", trong
khi hỗ trợ SVG chỉ giới hạn ở "the SVG Tiny Specification". [reported] Hiểu
đơn giản thì đó là ngược với ưu tiên của repo này: ThorVG *đọc* Lottie rất
mạnh, *đọc* SVG thì yếu, còn *ghi* SVG thì hoàn toàn không.

### 11.3 Chỗ lệch quan trọng nhất

| Hướng | ThorVG | Ghi chú |
|---|---|---|
| Lottie vào → raster ra | có | render vào vùng nhớ của canvas phần mềm |
| Lottie vào → GIF ra | có | `tvg_saver_save_animation`, toàn bộ animation |
| Lottie vào → **file SVG ra** | **không** | không có saver SVG [confirmed] |
| Lottie vào → **scene vector đọc được** | **có** | Accessor + `tvg_shape_get_path`, các lệnh của nó ánh xạ thẳng sang M/L/C/Z của SVG (§ 10.5) [confirmed] |
| SVG vào → raster ra | có, tập con SVG Tiny | `tvg-svg2png` |
| Bất cứ thứ gì → Lottie ra | không | không có saver cho Lottie [confirmed] |

`moho2svg.py` là một bộ ghi SVG. ThorVG thì không, và sẽ không bao giờ là —
nhưng nó cũng không cần phải là. ThorVG có thể đảm nhiệm phần *hiểu Lottie*,
trả về một scene đã tính xong gồm path, transform, màu và gradient; còn phần
ghi SVG vẫn nằm ở phía chúng ta, nơi nó vốn đã có sẵn. Chia việc như vậy mới
là cách hữu ích, và § 13 dựa trên đúng điều đó.

---

## 12. Xuất một frame cụ thể

### 12.1 Pipeline, với ThorVG

Ghép lại từ các API đã xác nhận ở § 10. Đây là hình dung về công việc, không
phải code đã chạy thử.

1. `tvg_engine_init(threads)` — một lần mỗi tiến trình.
2. `tvg_lottie_animation_new()` → một handle animation.
3. `tvg_animation_get_picture(animation)` → picture mà nó sở hữu.
4. `tvg_picture_load(picture, path)` hoặc `tvg_picture_load_data(...)` cho
   một tài liệu trong bộ nhớ.
5. `tvg_picture_set_size(picture, w, h)` để chọn độ phân giải đầu ra.
6. `tvg_animation_get_total_frame(animation, &total)` — nhớ kiểm tra giá trị
   0, nó nghĩa là "not properly configured".
7. `tvg_animation_set_frame(animation, n)` — `n` là số thực trong
   `[0, total - 1]`. Coi `TVG_RESULT_INSUFFICIENT_CONDITION` là thành công.
8. `tvg_swcanvas_create` + `tvg_swcanvas_set_target(buffer, stride, w, h, cs)`.
9. `tvg_canvas_add(canvas, picture)`.
10. `tvg_canvas_update` → `tvg_canvas_draw(canvas, true)` → `tvg_canvas_sync`.
11. Đọc vùng nhớ đó ra. Tự mã hóa lấy — ThorVG không có saver PNG.
12. `tvg_animation_del`, `tvg_canvas_destroy`, `tvg_engine_term`.

Bước 11 là chỗ người ta hay quên. `savers` chỉ có GIF (§ 9.2), nên muốn ra PNG
thì phải tự viết code mã hóa vùng nhớ ABGR/ARGB đó. Công cụ `tvg-svg2png` tự
lo phần này cho nó bằng cách nhúng thẳng `lodepng.cpp` vào thư mục của mình.
[confirmed]

### 12.2 Cách đánh số frame

Ba con số khác nhau, rất dễ lẫn:

| Đại lượng | Nằm ở đâu | Ý nghĩa |
|---|---|---|
| Lottie `ip` / `op` | tài liệu | frame đầu và frame cuối của composition, theo đánh số riêng của tài liệu |
| ThorVG `totalFrame()` | animation | tổng số frame; chỉ số frame chạy từ 0 .. total-1 |
| ThorVG `duration()` | animation | giây |

Chỉ số frame của ThorVG luôn bắt đầu từ 0, bất kể `ip` của tài liệu là bao
nhiêu. [confirmed từ header: "Frame numbering starts from 0"] Nếu một file
Lottie có `ip: 30` thì frame 30 theo cách đánh số của nó chính là frame 0 của
ThorVG. **Cờ `--frame` mà người dùng nhìn thấy bắt buộc phải nói rõ nó dùng
cách đánh số nào.** [inferred]

`tvg_animation_set_segment` lại đánh số lại lần nữa (§ 10.1), việc chọn marker
cũng vậy, nên không được dùng lẫn hai thứ này một cách cẩu thả — header ghi
rằng khi đã đặt marker thì dải của segment "will be disregarded".
[confirmed]

### 12.3 "Một frame" có thể là gì

| Đầu ra | Khả thi với ThorVG? | Cách làm |
|---|---|---|
| PNG / ảnh raster | có | render vào bộ đệm, tự mã hóa |
| GIF (một frame) | gượng ép | saver nhận cả một animation, không nhận một frame |
| **file SVG, do ThorVG tự ghi** | **không** | không hề có saver SVG [confirmed] |
| **file SVG, do ta tự ghi từ scene của ThorVG** | **về nguyên tắc là có** | duyệt scene bằng Accessor rồi xuất ra (§ 10.5) — chưa kiểm thử |
| Dữ liệu vector trong bộ nhớ | có | `tvg_shape_get_path` trả về các lệnh và điểm [confirmed] |

Vậy có hai đường để lấy được ảnh **vector** của một frame Lottie: để ThorVG
tính tài liệu rồi ta xuất ra những gì nó tạo được (§ 13.4), hoặc tự tính tài
liệu Lottie rồi xuất SVG trực tiếp (§ 13.5). Cả hai đường đều đi về bộ ghi SVG
mà `moho2svg.py` đã có sẵn.

---

## 13. Các phương án tích hợp cho repo này

Các ràng buộc hiện tại, từ [`CLAUDE.md`](../../CLAUDE.md) và nguồn: `moho2svg.py`
là một file duy nhất, chỉ dùng thư viện chuẩn, với Pillow là phụ thuộc *tùy
chọn* được import bên trong khối `try`. Các import của nó gồm `argparse`,
`base64`, `io`, `json`, `math`, `os`, `random`, `re`, `struct`, `sys`,
`zipfile`, cộng `dataclasses`, `enum` và `typing`. [confirmed] Hiện chưa có
import `zlib` nào, và cũng chưa có test suite.

### 13.1 Phương án A — gói `thorvg-python`

Một binding ctypes của bên thứ ba. [confirmed từ metadata PyPI và README của nó]

| Thuộc tính | Giá trị |
|---|---|
| Gói | `thorvg-python`, phiên bản 1.1.3 |
| Repo | `github.com/laggykiller/thorvg-python` |
| Giấy phép ghi trong metadata PyPI | LGPL-2.1 (lưu ý: bản thân ThorVG là MIT) |
| Yêu cầu | Python >= 3.7 |
| Wheels | macOS universal2 / x86_64 / arm64, manylinux x86_64 / aarch64 / i686 / ppc64le / s390x, Windows 32 / amd64 / arm64 |
| Bản ThorVG đi kèm | "Version bundled is the version available on Conan (Currently 1.0.4)" |
| Pillow | tùy chọn, chỉ cần cho `SwCanvas.get_pillow()` |

README của nó cho thấy đúng luồng mà chúng ta cần:

```python
import thorvg_python as tvg

engine = tvg.Engine(threads=4)
canvas = tvg.SwCanvas(engine)
canvas.set_target(512, 512)

animation = tvg.LottieAnimation(engine)
picture = animation.get_picture()
picture.load("tests/test.json")
picture.set_size(512, 512)
canvas.push(picture)

result, total_frame = animation.get_total_frame()
animation.set_frame(i)
canvas.update(); canvas.draw(True); canvas.sync()
im = canvas.get_pillow()
```

**Điểm mạnh:** không cần compiler, wheel đã gói sẵn thư viện native, có bản
build cho mọi nền tảng mà dự án này có thể chạy, và nó trả về luôn một ảnh
Pillow — thứ mà repo này vốn đã phụ thuộc ở mức tùy chọn.

**Điểm yếu:** đây là một phụ thuộc bên thứ ba bắt buộc, trong một dự án hiện
không có phụ thuộc nào; bản ThorVG đi kèm (1.0.4) tụt lại so với bản mới nhất
(1.1.0); trường giấy phép trên PyPI ghi LGPL-2.1, tức là ràng buộc khác với
giấy phép MIT của ThorVG, cần kiểm tra cho kỹ trước khi dùng.

### 13.2 Phương án B — dùng `ctypes` gọi `libthorvg` cài sẵn trên máy

Gọi thẳng API C bằng `ctypes` của thư viện chuẩn.

**Điểm mạnh:** không thêm phụ thuộc Python nào; dùng được đầy đủ API mới nhất;
hợp với phong cách "chỉ stdlib, phần thêm là tùy chọn" của code hiện có.

**Điểm yếu:** người dùng phải tự cài ThorVG, **và bản đó phải được build với
`-Dbindings=capi`**, vốn *không phải* mặc định (§ 9.2). Một bản build từ
Homebrew hay từ distro có thể không có ký hiệu C nào cả. Chúng ta còn phải tự
viết tay các khai báo kiểu `Tvg_*` rồi giữ chúng đồng bộ, và phải tự dò đường
dẫn thư viện trên cả ba nền tảng. Việc chẩn đoán khi máy người dùng cài hỏng
sẽ thành gánh nặng hỗ trợ của chúng ta.

### 13.3 Phương án C — gọi công cụ ThorVG từ bên ngoài

Bị loại vì bằng chứng, không phải vì sở thích. Cả `tvg-svg2png` lẫn
`tvg-lottie2gif` đều không nhận đối số frame, và cả hai đều tắt sẵn khi build
(`tools` mặc định là `''`). [confirmed] Phương án này đòi hỏi tự viết và tự
phát hành một công cụ C++ riêng — một thay đổi lớn hơn nhiều so với mọi phương
án khác ở đây.

### 13.4 Phương án D — ThorVG tính, chúng ta xuất scene ra SVG

Nạp file Lottie bằng ThorVG, đặt frame, rồi **không raster hóa**. Duyệt scene
thu được bằng Accessor (§ 10.5) và ghi SVG từ path, transform, màu và gradient
mà nó trả về.

**Điểm mạnh:** có đầu ra vector *mà không phải viết lại Lottie từ đầu*. ThorVG
gánh phần khó — tính keyframe, easing, precomp, time remap, modifier, matte —
còn phần chúng ta làm đúng là phần repo này vốn đã làm tốt. Các lệnh path của
ThorVG đúng là M/L/C/Z của SVG [confirmed], nên chuyển đổi hình học gần như
chỉ là chép lại. Cách này cũng né được mọi khoảng trống kiểu "schema không
định nghĩa chỗ này" ở § 6.4 và § 8.3, vì ThorVG đã tự quyết những chỗ đó rồi.

**Điểm yếu:** chưa được chứng minh — xem ghi chú "chưa kiểm chứng" ở § 10.5.
Nó cũng thừa hưởng các điểm mù của ThorVG: text không có hàm đọc đường viền
glyph, còn effect raster thì không có dạng vector. Và kết quả là *cách ThorVG
hiểu* file đó — chỉ đúng nếu ThorVG hiểu đúng.

### 13.5 Phương án E — tự tính Lottie, không dùng ThorVG

Tự đọc JSON Lottie, tự tính mọi property tại frame N theo § 4 và § 8, rồi
xuất SVG qua bộ máy mà `moho2svg.py` đã có.

**Điểm mạnh:** có đầu ra vector mà **không thêm phụ thuộc nào cả**, và kiểm
soát hoàn toàn kết quả — kể cả giữ được những cấu trúc Lottie mà ThorVG sẽ làm
phẳng đi. Schema trong `lottie/` là một đặc tả đầu vào hoàn chỉnh và máy đọc
được, tức là điểm xuất phát tốt hơn nhiều so với những gì định dạng Moho từng
có. Về mặt khái niệm, đây đúng là việc mà code hiện có đang làm: keyframe thưa
trên các channel độc lập, tính tại một frame, rồi ghép qua một ngăn xếp
transform — so sánh với
[`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 2 và
§ 3.

**Điểm yếu:** đây là phương án tốn công nhất, và tính đúng đắn chỉ chứng minh
được bằng một player thật. Những phần khó lại đúng là những phần schema không
định nghĩa: ngữ nghĩa của shape modifier và quy tắc thứ tự "neighbouring
shapes" (§ 6.4), thứ tự kết hợp `st`/`sr` (§ 8.3), và đơn vị của precomp time
remap (§ 8.3). Còn effect, layer style và text thì gần như không có giới hạn
phạm vi.

### 13.6 So sánh

| | A: `thorvg-python` | B: `ctypes` trực tiếp | C: công cụ đi kèm | D: ThorVG + duyệt scene | E: tự tính toán |
|---|---|---|---|---|---|
| Đầu ra vector | không | không | không | có | có |
| Đầu ra raster | có | có | không (không có cờ frame) | có | không |
| Phụ thuộc mới | một, tùy chọn | không, nhưng cần thư viện cài sẵn trên máy | một công cụ C++ phải tự viết | giống A hoặc B | không |
| Ai bảo đảm đúng Lottie | ThorVG | ThorVG | — | ThorVG | chúng ta, và phải tự chứng minh |
| Khối lượng công việc | nhỏ | trung bình | lớn | trung bình | lớn |
| Mức đã kiểm chứng | API đã xác nhận | API đã xác nhận | đã loại, có bằng chứng | **chưa kiểm chứng** | — |

### 13.7 Khuyến nghị

Lựa chọn phụ thuộc vào một câu hỏi chưa có lời đáp: **đầu ra cần là raster hay
vector?**

- Nếu là **raster** (một file PNG của frame N): chọn **Phương án A**. Thêm
  `thorvg-python` như một phụ thuộc *tùy chọn*, bọc trong `try: import ...`
  đúng như cách đang xử lý Pillow, và báo lỗi rõ ràng khi thiếu nó. Đây là
  thay đổi nhỏ nhất mà vẫn cho kết quả đúng và đầy đủ tính năng, vì ThorVG hỗ
  trợ Lottie đầy đủ hơn nhiều so với những gì chúng ta có thể tự làm. Độ tin
  cậy: cao.
- Nếu là **vector** (một file SVG của frame N) — khả năng cao đây mới là ý
  định thật, xét theo mục đích của repo này — thì **hãy thử Phương án D trước
  khi chốt Phương án E**. Phương án D tận dụng lại phần Lottie mà ThorVG đã
  làm, còn ta chỉ lo ghi SVG — đúng thứ codebase này vốn làm tốt. Phương án E
  tốn gấp vài lần công sức, và những phần khó nhất của nó lại rơi đúng vào chỗ
  schema không nói tới (§ 6.4, § 8.3). Độ tin cậy rằng nên thử D trước: trung
  bình — vì nó dựa trên giả định chưa kiểm chứng ở § 10.5.

**Bước tiếp theo rẻ nhất là một spike, không phải một bản thiết kế.** Cài
`thorvg-python`, nạp một file Lottie, đặt một frame, duyệt scene bằng
Accessor, rồi in ra những gì nhận được. Chỉ một thử nghiệm đó là đủ để trả lời
câu hỏi mở ở § 10.5 và chọn giữa D với E. Chưa chạy nó thì mọi việc thiết kế
tiếp theo đều chỉ là suy đoán.

Dù chọn hướng nào, ThorVG vẫn giữ một vai trò thứ hai rất đáng giá: làm
**renderer tham chiếu**. Render frame N bằng ThorVG, render lại bằng code của
mình, rồi so sánh. Đó đúng là phương pháp "so với bản xuất tham chiếu" mà phía
Moho của repo này được xây dựng trên — xem
[`moho-project-file-format.md`](moho-project-file-format.md) § 1 — khác ở chỗ
bản tham chiếu ở đây miễn phí và script hóa được, thay vì phải xuất tay từ một
ứng dụng GUI.

❓ Raster hay vector là quyết định về sản phẩm. Không bằng chứng nào trong tài
liệu này chốt được điều đó.

---

## 14. Ánh xạ giữa Moho và Lottie

Mục này so sánh ở mức khái niệm, để các quyết định thiết kế sau này có chỗ
bám. Nó **không** phải kế hoạch triển khai, và không ánh xạ nào dưới đây đã
được kiểm thử.

### 14.1 Chỗ hai định dạng giống nhau

| Khái niệm | Moho | Lottie | Nhận xét |
|---|---|---|---|
| Container | tài liệu JSON | tài liệu JSON | trực tiếp |
| Keyframe thưa theo property | `Channel` — `{"when": [...], "val": [...]}` | `property` — `{"a": 1, "k": [keyframes]}` | cùng ý tưởng, khác cách bố trí: Moho dùng các mảng song song, Lottie dùng một mảng các đối tượng |
| Thời gian dựa trên frame | số frame | số frame, giá trị thực | trực tiếp |
| Path Bezier bậc ba | được `BezierReconstructor` tái dựng thành các điểm điều khiển tường minh | `values/bezier` với `v` / `i` / `o` | gần — xem § 14.2 |
| Cây layer với transforms | các layer lồng nhau | danh sách phẳng cộng `parent` theo `ind` | cùng ngữ nghĩa, mã hóa khác |
| Style fill và stroke | `StyleTable` / `ResolvedStyle` | `fl` / `st` / `gf` / `gs` | tương ứng trực tiếp trong các trường hợp thông thường |
| Gradient | linear và radial | `gradient-type` 1/2/3 | Lottie cũng có conic |
| Opacity layer | channel | `ks.o` | trực tiếp |
| Masking, hai trường | `group_mask` + `masking` trên từng layer con | `tt` / `tp` / `td`, cộng `masksProperties` | giống về tinh thần, khác về cơ chế |

### 14.2 Biểu diễn Bezier

Cuối cùng thì cả hai định dạng đều mô tả Bezier bậc ba bằng tiếp tuyến
**tương đối**, và đó là một điểm thuận lợi thật sự. Schema của Lottie nói điểm
`i` và `o` là "relative to the corresponding `v`" [confirmed]; còn
`BezierReconstructor` của `moho2svg.py` thì dựng ra các điểm điều khiển tường
minh từ cách mã hóa smoothness / weight / offset của Moho.

Khác biệt nằm ở chỗ công sức đổ vào đâu. Moho lưu đường cong ở dạng *ngầm*,
phải dựng lại bằng một công thức khớp theo kinh nghiệm — docstring của module
trong `moho2svg.py` ghi lại lý do. Lottie thì lưu thẳng các điểm điều khiển.
Nên **Moho → Lottie là hướng có mất mát nhưng tính được** (dựng lại, rồi ghi),
còn **Lottie → Moho mới là hướng khó** (phải đảo ngược một phép khớp kinh
nghiệm). Chỉ hướng thứ nhất là liên quan tới repo này.

Một khác biệt về cấu trúc cần lưu ý: danh sách `edges` của shape Moho là một
tập không có thứ tự, `PathTracer` phải dò lại thành các vòng khép kín (xem
[`moho-export-pipeline.md`](moho-export-pipeline.md) § 6). Trong khi
`values/bezier` của Lottie vốn đã là danh sách đỉnh có thứ tự, kèm cờ `c` cho
biết đường có khép kín hay không. Vậy bước dò đó tạo ra đúng thứ tự mà Lottie
cần — phần việc này coi như đã xong. [inferred]

### 14.3 Chỗ hai định dạng khác nhau

| Khái niệm Moho | Khái niệm Lottie gần nhất | Khoảng chênh |
|---|---|---|
| Bone và skinning (bind cứng và mềm) | **không có** | Lottie không có skeleton. Biến dạng bone phải được **bake** (tính sẵn) vào vị trí đỉnh theo từng frame. Xem [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md). |
| Smart Bones (một dial bone chọn pose bằng cách đảo ngược một pose curve) | không có | phải tính trước rồi bake |
| Kết hợp shape boolean `combo_mode` | `shapes/merge` (`mm`: 1 normal, 2 add, 3 subtract, 4 intersect, 5 exclude) | các enum nhìn thì tương đương, nhưng `combo_mode` 2 của Moho [vẫn được ghi là chưa giải quyết](moho-project-file-format.md), còn phần merge của Lottie thì nổi tiếng là không đồng đều giữa các player |
| Họa tiết cọ (các dab đóng dấu, kho `.mohobrush`) | không có | Lottie không có stroke có họa tiết. Các nhánh raster hiện có sẽ phải chuyển thành asset ảnh, nếu không thì mất chi tiết |
| Stroke thon dần (Moho lùi về hình học đường viền được tô) | không có | vẫn dùng cách lùi đó: xuất đường viền thành một path tô màu |
| Switch layer (chọn rời rạc layer con đang hoạt động) | không có tương đương trực tiếp | có thể diễn đạt bằng khoảng hiển thị `ip`/`op` của layer [inferred] |
| `PatchLayer` (dùng lại mesh của layer khác ở một vị trí vẽ khác) | không có | Lottie không có cơ chế tham chiếu dùng chung; hình học sẽ bị nhân đôi |
| Hệ tọa độ: 2 đơn vị trải hết chiều cao canvas, y hướng lên | pixel, y hướng xuống, gốc trên-trái | một ánh xạ tuyến tính cố định, đã được viết ra trong [`moho-project-file-format.md`](moho-project-file-format.md) § 4 |
| Góc tính bằng radian | độ (`r`, `sk`, `sa` đều "in degrees") | chuyển đổi đơn vị |
| Màu 0..1 trong channel, 0..255 ở một số trường thường | mảng 0..1, trừ `solid-layer.sc` là `#RRGGBB` | cả hai định dạng đều tự mâu thuẫn, chỉ khác chỗ |

### 14.4 Nói thẳng về hướng Moho → Lottie

Mọi thứ Moho làm được mà Lottie không diễn tả nổi — bone, Smart Bones, họa
tiết cọ, patch layer — đều chỉ có một cách xử lý: **bake nó tại một frame đã
chọn**. Cách đó cho ra một ảnh tĩnh đúng; muốn thành hoạt ảnh thì phải bake
mọi frame, mà làm vậy thì mất luôn ý nghĩa của một định dạng hoạt ảnh.

Nên xuất Moho → Lottie ở dạng *hoạt ảnh* mà vẫn trung thành là một dự án lớn
hơn nhiều so với xuất Moho → Lottie *một frame*. Khác biệt không nằm ở công
sức, mà ở chỗ cái rig có sống sót qua chuyến đi hay không. Câu trả lời là
không. [inferred, nhưng suy ra trực tiếp từ việc Lottie không có khái niệm
skeleton]

---

## 15. Các khoảng trống đã biết và câu hỏi mở

Sắp theo mức ảnh hưởng tới tính năng dự kiến.

1. **Đầu ra là raster hay vector?** Chưa chốt, mà nó quyết định toàn bộ kiến
   trúc (§ 13.7). Mọi thứ khác đều phụ thuộc vào câu này.
2. **Một scene ThorVG nạp từ Lottie có duyệt và đọc lại được không?** (§ 10.5)
   Nếu được, Phương án D gỡ bỏ gần hết công việc của Phương án E. Chưa kiểm
   thử, mà kiểm thử thì rẻ, và đây là thử nghiệm đáng giá nhất được nêu trong
   tài liệu này. Các câu hỏi con: một `Picture` có để lộ node con cho Accessor
   không; hình học đọc về là tọa độ cục bộ hay đã gộp; text thì sao.
3. **Cờ `--frame` dùng cách đánh số của ai** — của tài liệu (tính từ `ip`) hay
   của ThorVG (tính từ 0)? Hai cách này lệch nhau mỗi khi `ip != 0` (§ 12.2).
4. **Thứ tự kết hợp `st` và `sr` không được schema định nghĩa** (§ 8.3). Công
   thức thông thường ở đó mới chỉ là suy luận, phải kiểm chứng với một renderer
   trước khi cho bất kỳ bộ tính toán nào dựa vào.
5. **Đơn vị của precomp time remap.** Schema nói `tm` ánh xạ "frame index →
   time in seconds", tức là đổi đơn vị so với mọi thứ xung quanh (§ 8.3). Nên
   xác nhận lại với một player.
6. **Quy tắc thứ tự các phần tử shape không nằm trong schema** (§ 6.4). "Style
   applies to neighbouring shapes" không phải câu có thể kiểm bằng máy. Bộ ghi
   Lottie nào chúng ta làm ra cũng cần một renderer để đối chiếu.
7. **Giấy phép của `thorvg-python`.** Metadata trên PyPI ghi LGPL-2.1 trong
   khi ThorVG là MIT (§ 13.1). Chưa đối chiếu với file LICENSE trong repo của
   nó. Phải chốt trước khi quyết định dùng.
8. **Mức hỗ trợ Lottie thật sự của ThorVG chưa được định lượng ở đây.** Câu
   "extensive support" là do chính dự án nói [reported]. Chưa có rà soát nào
   theo từng tính năng, mà effect, layer style và text lại là những điểm yếu
   thường thấy ở mọi player.
9. **Không có gì trong tài liệu này được chạy thật.** Chưa render file Lottie
   nào, chưa build ThorVG lần nào, chưa cài gói Python nào. Các mục 2 đến 8
   kiểm chứng được bằng các file trong repo này; các mục 9 đến 13 kiểm chứng
   được bằng các nguồn đã dẫn URL; mục 14 là phần phân tích.

---

## 16. Cách kiểm lại các con số của schema

Mọi con số và bảng trường trong các mục 2 đến 8 đều tạo lại được. Các script
dưới đây chạy trên bản schema nằm trong repo này và không cần gói bên thứ ba.

Chạy từng cái ở thư mục gốc của repo. Dạng heredoc giúp khỏi phải escape
`$defs` trong shell.

```bash
# Module and definition counts (§ 2.2)
python3 - <<'EOF'
import json
d = json.load(open('lottie/lottie.schema.json'))['$defs']
print('modules:', len(d), 'defs:', sum(len(v) for v in d.values()))
for k, v in d.items():
    print(f'  {k:15} {len(v):3}')
EOF
```

```bash
# Enumeration values (§ 5, § 6)
python3 - <<'EOF'
import json
c = json.load(open('lottie/lottie.schema.json'))['$defs']['constants']
for k, v in c.items():
    vals = ', '.join(f"{o.get('const')!r}={o.get('title')}" for o in v.get('oneOf', []))
    print(f'{k}: {vals}')
EOF
```

```bash
# Bundled vs split equivalence (§ 1.1, § 2.4)
python3 - <<'EOF'
import json, re
b = json.load(open('lottie/lottie.schema.json'))['$defs']

def norm(o):
    """Drop per-file $schema/$id and rewrite split-tree $ref URLs to bundle form."""
    if isinstance(o, dict):
        return {k: (re.sub(r'^.*#/\$defs/', '#/$defs/', v)
                    if k == '$ref' and isinstance(v, str) else norm(v))
                for k, v in o.items() if k not in ('$schema', '$id')}
    if isinstance(o, list):
        return [norm(x) for x in o]
    return o

same = diff = 0
for mod, items in b.items():
    for name, node in items.items():
        s = json.load(open(f'lottie/schema/{mod}/{name}.json'))
        if norm(s) == norm(node):
            same += 1
        else:
            diff += 1
            print('differs:', mod, name)
print('identical:', same, 'differing:', diff)
EOF
```

Kết quả mong đợi của script cuối: `differs: layers unknown-layer`,
`differs: shapes unknown-shape`, `identical: 157 differing: 2`. [confirmed —
các con số ở § 1.1 và § 2.4 chính là từ lần chạy này]

Các con số về ThorVG ở mục 9 và 10 kiểm lại được bằng cách tải các file nêu ở
§ 1.3 từ repo `thorvg/thorvg` nhánh `main` rồi đọc trực tiếp; mọi chữ ký hàm
trích trong tài liệu này đều xuất hiện nguyên văn trong
`src/bindings/capi/thorvg_capi.h`.
