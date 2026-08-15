# Xuất SVG từ file dự án Moho

> Bản dịch tiếng Việt của `docs/moho-exporting-svg.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Tài liệu này giải thích cách dùng `moho2svg.py` để xuất artwork vector từ một
file dự án Moho (`.mohoproj` / `.animeproj`) sang SVG. Về cấu trúc của bản thân
file dự án, xem [`moho-project-file-format.md`](moho-project-file-format.md).
Về toàn bộ lập luận theo từng bằng chứng cho mọi công thức và hằng số mà công
cụ này dùng, xem module docstring ở đầu `moho2svg.py` — tài liệu này là hướng
dẫn sử dụng, không thay thế nó.

## 1. Yêu cầu

- Python 3, không cần gói bên thứ ba bắt buộc (chỉ stdlib).
- **Pillow, tùy chọn nhưng khuyến nghị** (`pip install Pillow`) — nếu không có
  nó, việc xuất tài liệu có kiểu brush có họa tiết vẫn hoạt động, nhưng kết quả
  có thể rất chậm (hoặc không mở được) trong trình duyệt/trình xem SVG. Xem
  [§ 7](#7-họa-tiết-cọ-brush).
- Một file dự án Moho: `.mohoproj` (Moho Pro) hoặc `.animeproj` (Moho Debut).
  Cả hai đều là JSON thuần dù có phần mở rộng khác.
- Tùy chọn: một trình xem SVG để kiểm tra nhanh đầu ra — trình duyệt dùng được;
  `rsvg-convert` tiện cho việc render PNG theo script.

## 2. Lệnh cơ bản

```bash
# Liệt kê mọi layer trong tài liệu (số điểm/shape của mesh cho layer vector)
python3 moho2svg.py Project.mohoproj --list

# Xuất một layer vector có tên cụ thể ra file SVG riêng
python3 moho2svg.py Project.mohoproj --layer Arm_B --out Arm_B.svg

# Xuất mọi layer vector, mỗi layer một file
python3 moho2svg.py Project.mohoproj --all --outdir svg/

# Xuất toàn bộ tài liệu thành một SVG nhiều lớp
python3 moho2svg.py Project.mohoproj --combined Bandit.svg
```

Cần đúng một chế độ xuất: `--layer`, `--all`, `--combined`, hoặc `--list`.

## 3. Tham chiếu đầy đủ các cờ

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `project` (vị trí) | — | Đường dẫn tới file `.mohoproj`/`.animeproj`. |
| `--list` | — | In mọi layer (tên, loại, và số điểm/shape của mesh cho layer vector), rồi thoát. |
| `--layer NAME` | — | Xuất layer vector duy nhất có tên `NAME`. |
| `--out FILE` | `<layer>.svg` | Đường dẫn đầu ra cho chế độ `--layer`. |
| `--all` | — | Xuất mọi layer vector nhìn thấy được, mỗi layer một file. |
| `--outdir DIR` | `.` | Thư mục đầu ra cho chế độ `--all`. |
| `--combined FILE` | — | Xuất toàn bộ tài liệu thành một SVG nhiều lớp vào `FILE`. |
| `--flat` | tắt | Với `--combined`, bỏ `<g>` lồng nhau cho từng layer (làm phẳng cấu trúc nhóm). |
| `--frame N` | `0` | Khung hình hoạt ảnh nào được đánh giá (channels, bone pose, Smart Bone dials). |
| `--crop` | tắt | Dùng viewBox khít quanh nội dung xuất ra thay vì toàn bộ canvas. |
| `--local` | tắt | Bỏ qua transform của tổ tiên và biến dạng bone — xuất tọa độ điểm thô của mesh theo tỷ lệ canvas. Chỉ hợp lệ với `--layer`/`--all`. |
| `--include-hidden` | tắt | Cũng xuất/duyệt qua các layer có `visible: false` hoặc `edit_only: true`. |
| `--mask-container NAME` | (lặp được) | Ép layer `NAME` hoạt động như container masking dù `group_mask` chưa đánh dấu nó. Xem [Masking](#6-những-điểm-đặc-biệt-của-masking). |
| `--stroke-mul N` | `2.0` | Hệ số nhân độ rộng nét: `stroke_px = line_width * point_width * canvas_height * N / 2`. Dùng nếu hiệu chuẩn line-width của tài liệu trông lệch so với render của chính Moho. |
| `--brush-dir DIR` | `styles/Brushes` | Thư mục chứa asset brush (PNG họa tiết và thư mục brush nhiều khung) dùng để xấp xỉ kiểu nét "brush" có họa tiết. Truyền `""` để tắt hoàn toàn việc stamp brush. Xem [Họa tiết cọ](#7-họa-tiết-cọ-brush). |
| `--brush-spacing-mul N` | `1.0` | Nhân khoảng cách giữa các dab brush với `N` — tăng nó (ví dụ `3`-`4`) để giảm mật độ dab trên tài liệu nhiều brush, đánh đổi độ trung thực họa tiết lấy một SVG nhẹ hơn/mở nhanh hơn nhiều. Xem [Họa tiết cọ](#7-họa-tiết-cọ-brush). |
| `--brush-raster` | tắt | Gộp toàn bộ nét vẽ của mỗi shape có brush thành MỘT raster `<image>` thay vì một `<use>`/dab cho mỗi chấm — tùy chọn brush nhỏ/nhanh nhất, cái giá là nét đó không còn là vector. Cần Pillow. Xem [Họa tiết cọ § 7.2](#72-raster-hóa-toàn-bộ-nét-vẽ-thành-một-ảnh-cho-mỗi-shape). |
| `--brush-raster-supersample N` | `2.0` | Với `--brush-raster`, gộp ở kích thước `N` lần kích thước pixel của chính shape trước khi khai báo nó ở kích thước 1x trong SVG — họa tiết mịn sắc hơn với cái giá file tăng gần như `N²`. Xem [§ 7.2](#72-raster-hóa-toàn-bộ-nét-vẽ-thành-một-ảnh-cho-mỗi-shape). |

## 4. Quy trình làm việc điển hình

### Xem xét tài liệu trước khi xuất bất cứ thứ gì

```bash
python3 moho2svg.py Project.mohoproj --list
```

Đây là cách nhanh nhất để tìm tên chính xác của một layer (bug masking/hoạt ảnh
rất thường chỉ là sai tên) và xem layer nào thực sự mang mesh (chỉ những layer
đó mới xuất được).

### Xuất một nhân vật/rig thành một ảnh tham chiếu duy nhất

```bash
python3 moho2svg.py Project.mohoproj --combined Character.svg --crop
```

### Xuất từng phần của rig riêng lẻ (ví dụ để nhập lại từng mảnh vào nơi khác)

```bash
python3 moho2svg.py Project.mohoproj --all --outdir svg/ --crop
```

Các file được đánh số theo thứ tự vẽ (`00_`, `01_`, ...) nên nhập lại chúng
theo đúng thứ tự số sẽ tái tạo được thứ tự xếp từ sau ra trước như bản gốc.

### So sánh các khung hình của một hoạt ảnh

```bash
python3 moho2svg.py Project.mohoproj --combined frame0.svg --frame 0
python3 moho2svg.py Project.mohoproj --combined frame30.svg --frame 30
```

## 5. Bố cục riêng của repo này

Kho lưu trữ này giữ ba thư mục làm việc không thuộc về bản thân công cụ, chỉ
thuộc về cách tổ chức của bản checkout này:

- `moho/` — bản sao cục bộ các file nguồn `.mohoproj`/`.animeproj` dùng để phát
  triển và kiểm tra hồi quy (bị gitignore — đây là các file gần như nhị phân,
  lớn, thuộc về các dự án Moho đang được kiểm thử, không thuộc về công cụ).
- `out/svg/ori/` — bản xuất gốc (họa tiết brush đầy đủ); `out/svg/med/`,
  `out/svg/fast/`, `out/svg/raster/` — các bản xuất brush hiệu năng thay thế
  của cùng các dự án (tương ứng: mật độ dab giảm bớt, không có họa tiết brush,
  và một raster image cho mỗi shape). Xem [§ 7](#7-họa-tiết-cọ-brush).
- `out/lottie/` — các bản xuất Lottie (xem `moho-to-lottie-plan.md`).
- `styles/Brushes/` — xem [Họa tiết cọ](#7-họa-tiết-cọ-brush) bên dưới.

Mọi thứ dưới `out/` đều bị gitignore. Makefile dựng bất kỳ bản xuất nào từ
dòng lệnh — file đầu ra chính là target, ví dụ `make out/svg/ori/Bandit.svg`;
`make svg-all` dựng mọi dự án dưới `moho/` ở cả bốn dạng svg và `make
lottie-all` dựng bản xuất Lottie của mọi dự án. `out/svg/med/` giảm mật độ dab
(`BRUSH_SPACING_MUL`, mặc định 2), `out/svg/fast/` tắt stamp brush,
`out/svg/raster/` bake nét brush raster theo từng shape (xem `Makefile`).

## 6. Những điểm đặc biệt của masking

Mô hình masking của Moho dùng hai trường riêng biệt — `group_mask` của
container và giá trị `masking` của từng child — và nó áp dụng đồng nhất ở mọi
độ sâu lồng nhau, kể cả layer cấp cao nhất của tài liệu. Nếu masking của một
tài liệu có vẻ không có hiệu lực ở nơi bạn mong đợi, trước tiên hãy xác nhận
trong chính Moho layer nào là nguồn mask (masking của nó nên là 2, Moho hiển
thị kiểu "Add to Mask") so với layer nào nên bị *cắt* (masking của nó là
0/không đặt, hiển thị là "Mask This Layer" hoặc tương tự) — rồi kiểm tra lại
bằng `--list` rằng cả hai nằm dưới cùng một container. Nếu `group_mask` của
container thực sự không được nhận diện, hãy ép bằng `--mask-container NAME`.
Xem phần MASKING trong module docstring để biết đầy đủ các quy tắc và lý do
đằng sau chúng.

## 7. Họa tiết cọ (brush)

Outline của một style có tên có thể là "brush" có họa tiết (được stamp lặp đi
lặp lại dọc theo path với độ nhiễu xoay) thay vì một nét có độ rộng đồng nhất
— nghĩ đến một mảng hồng má mềm, một vệt bóng mực, hay nét gạch chéo vẽ tay.
Một `<path stroke>` SVG thuần không tái tạo được họa tiết đó, nên công cụ này
xấp xỉ nó bằng cách stamp chính các ảnh của brush dọc theo path, nhưng chỉ với
brush mà nó thực sự tìm được asset.

Để bật tính năng này, trỏ `--brush-dir` vào một thư mục chứa các file brush
liên quan (PNG đơn và/hoặc thư mục brush nhiều khung, đặt tên khớp với
`brush_name` của style — xem [Định dạng file dự án Moho § 8.6](moho-project-file-format.md#86-phân-giải-brush_name-thành-một-file)
để biết chính xác tên đó được phân giải thành file như thế nào). Nguồn đơn giản
nhất cho các file này là chính bản cài đặt Moho, nó đi kèm mọi brush mà nó
dùng:

```bash
cp -R /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/
```

(điều chỉnh đường dẫn nếu bản cài đặt của bạn ở nơi khác). Lệnh này sao chép
thư mục brush của Moho vào `styles/Brushes` — `cp` thường không copy được thư
mục trên macOS, nên bắt buộc có `-R`. `styles/` là nội dung cục bộ không
track, không phải phần của kho lưu trữ.

Bất kỳ brush nào không phân giải được asset (kể cả khi `styles/Brushes` không
tồn tại) sẽ rơi về một nét đều đặn đơn giản — không có gì thoái lui cho một
checkout chưa chạy lệnh sao chép.

### 7.1 Hiệu năng: cài Pillow

Một tài liệu mà nét vẽ dùng brush có họa tiết rộng rãi (thay vì chỉ một hoặc
hai shape điểm nhấn) có thể kết thúc với hàng nghìn dab được stamp riêng lẻ
một khi mọi style khớp đều nhận nó. Việc nó tốn kém bao nhiêu *khi xem* (không
phải khi tạo — bản thân `moho2svg.py` vẫn nhanh trong cả hai trường hợp) phụ
thuộc hoàn toàn vào việc **Pillow** (`pip install Pillow`) có được cài ở nơi
bạn chạy `moho2svg.py` hay không:

- **Đã cài Pillow (ưu tiên)**: mỗi tổ hợp *(brush, frame, màu, alpha)* thực sự
  được dùng trong tài liệu được pre-render, một lần, thành một PNG đã tô màu
  ngay lúc xuất (`Exporter._bake_tinted_frame`). Mỗi dab sau đó chỉ là một
  `<use>` của ảnh đó — một thao tác blit ảnh đơn giản, rẻ, tăng tốc bằng phần
  cứng cho mọi trình xem.
- **Không có Pillow (fallback, không thêm dependency nào)**: mỗi dab là một
  `<g>` được mask bởi một `<mask>`+`<feColorMatrix>` filter dùng chung, tô màu
  lại họa tiết thô ngay lúc render (xem [§ 7.3](#73-vì-sao-đường-fallback-tốn-kém-khi-xem)
  để biết vì sao chính điều này — chứ không phải số dab hay kích thước file
  riêng lẻ — là thứ làm trình xem chậm hoặc không mở được file).

Đã xác nhận ở cùng độ rộng preview 600px (`rsvg-convert`), fallback so với
đường Pillow:

| Tài liệu | Fallback (mask+filter) | Pillow (pre-tinted `<use>`) |
|---|---|---|
| SketchBone | 3.89 MB / 15.97s | 2.86 MB / **2.46s** |
| AddBone | 6.16 MB / 25.83s | 9.00 MB / **8.90s** |
| WhatIsBone | 4.11 MB / 6.13s | 9.62 MB / **1.84s** |

Cài Pillow là một lợi ích 3x-6.5x về thời gian render trên toàn bộ các tài
liệu — nhưng chú ý không phải lúc nào cũng là *file nhỏ hơn*: AddBone và
WhatIsBone thực tế lớn hơn, vì việc pre-tint bake mỗi màu riêng biệt ở độ phân
giải gốc của chính họa tiết nguồn (lên tới 512x512 với một số brush đi kèm
Moho), và rig này dùng đủ tổ hợp (brush, màu) riêng biệt để các PNG được bake
vượt trội hơn các def mask/filter mà chúng thay thế. Nếu kích thước file cụ
thể quan trọng hơn tốc độ render với một tài liệu như vậy, đường fallback
(không Pillow, hoặc chạy trong môi trường không có nó) vẫn có thể được ưu tiên,
hoặc kết hợp với `--brush-spacing-mul` bên dưới.

Hai cờ nữa quản lý khối lượng dab, độc lập với đường render đang hoạt động:

- **`--brush-spacing-mul N`** (ví dụ `3` hoặc `4`) làm giảm mật độ dab trên
  toàn tài liệu, nhân khoảng cách giữa các dab trong khi mọi thứ khác (kể cả
  bản thân `--brush-dir`) không đổi. Điều này cắt số dab gần như tỷ lệ thuận
  với `N` (đã xác nhận trên đường fallback ở độ rộng 900px: `N=4` đưa
  SketchBone từ 17,822 dab/~31s xuống 4,502 dab/~8s), cái giá là họa tiết thô
  hơn, nhiều "chấm" hơn thay vì liên tục. `N=2`-`2.5` là điểm giữa hợp lý cho
  hầu hết tài liệu — vẫn là một mức giảm lớn, mà họa tiết vẫn đọc là liên tục
  ở kích thước xem bình thường.
- **`--brush-dir ""`** (hoặc pattern rule `out/svg/fast/%.svg`, làm chính
  xác điều này cho bất kỳ dự án nào, ghi vào `out/svg/fast/` bị gitignore
  thay vì `out/svg/ori/`) tắt hoàn toàn việc stamp brush để có một preview
  nhanh, nhẹ — mọi nét
  có brush đều rơi về nét đơn giản hoặc (nếu tapered) ribbon của
  TaperedStrokeOutliner, cả hai đều rẻ cho mọi trình xem bất kể Pillow. Đã xác
  nhận trên SketchBone: 3.9 MB → 319 KB, và thời gian render giảm xuống dưới
  0.1 giây. Dùng nó bất cứ khi nào bạn cần nhìn nhanh tương tác vào một tài
  liệu và không cần bản thân họa tiết brush; quay lại bản xuất `--brush-dir`
  đầy đủ cho đầu ra cuối/in ấn.

### 7.2 Raster hóa toàn bộ nét vẽ thành một ảnh cho mỗi shape

`--brush-raster` đi xa hơn đường Pillow ở trên: thay vì một `<use>` cho mỗi
dab, `Exporter._raster_brush_shape` gộp các dab của TOÀN BỘ một shape có brush
thành một raster `<image>` duy nhất ngay lúc xuất (cũng qua Pillow — rơi về
đường per-dab bình thường, kèm cảnh báo, nếu Pillow không có). Đây là tùy chọn
brush mạnh nhất của công cụ này, đánh đổi hoàn toàn tính vector của nét đó (nó
trở thành bitmap cố định — không còn co giãn hay chỉnh sửa được như path sau
này) lấy kết quả nhỏ nhất và nhanh nhất để xem trong số mọi tùy chọn ở đây:

| Tài liệu | Pillow, per-dab `<use>` | `--brush-raster` (1x) | `--brush-raster` (mặc định, 2x) |
|---|---|---|---|
| SketchBone | 2.86 MB / 2.46s | 0.93 MB / 0.15s | **2.74 MB** / **0.18s** |
| AddBone | 9.00 MB / 8.90s | 0.44 MB / 0.07s | **1.03 MB** / — |
| WhatIsBone | 9.62 MB / 1.84s | 0.32 MB / 0.09s | **0.51 MB** / — |

Kể cả ở 2x, `--brush-raster` vẫn nhỏ hơn đường per-dab `<use>` trên mọi tài
liệu đã thử (và nhanh hơn nhiều để render trên cả ba) — nó sửa đúng sự thoái
lui kích thước file mà đường per-dab mắc phải trên AddBone/WhatIsBone (§ 7.1),
vì một ảnh gộp cho mỗi *shape* tăng theo số shape, không tăng theo số tổ hợp
(brush, màu) riêng biệt lấy từ một họa tiết gốc có thể rất lớn.

**Sự đánh đổi tìm thấy khi kiểm thử, ngoài việc mất khả năng chỉnh sửa
vector**: ở 1:1 (không supersample), một nét có chi tiết rất mịn, thưa, tương
phản cao dưới sự chồng dab dày (đã xác nhận trên shadow "golge" của rig
SketchBone — chính shape dùng xuyên suốt tài liệu này để minh họa các vấn đề
brush, chồng dab ~30-50x) mất đi họa tiết mảnh giống sợi tóc mà đường per-dab
`<use>` giữ được, ra kết quả mềm/mờ hơn.

**`--brush-raster-supersample N` (mặc định 2.0)** phục hồi đáng kể điều này:
canvas được gộp ở kích thước gấp N lần kích thước pixel của chính shape rồi
khai báo ở kích thước 1x bình thường trong SVG — thủ thuật "@2x asset" chuẩn
cho bitmap DPI cao, cho trình xem thu nhỏ thêm chi tiết nguồn để làm việc. Đã
xác nhận trên "golge" ở độ rộng preview 500px: 1x đọc như một khối mềm gần như
phẳng, 2x phục hồi một viền hạt nhìn thấy được (dù hơi mềm), 3x đọc gần như
các sợi mảnh của bản per-dab `<use>`. Thời gian render gần như không đổi với N
(vẫn là một lần blit ảnh cho mỗi shape trong mọi trường hợp — 0.13s/0.18s/0.24s
cho SketchBone ở N=1/2/3), nhưng kích thước file tăng gần như theo N²
(0.93/2.74/5.42 MB cho cùng tài liệu) — qua N≈3 bạn đang tiến gần hoặc vượt
kích thước của chính đường per-dab `<use>` cho một tài liệu nặng họa tiết, lúc
đó đường mặc định đó (vốn không hề mất chi tiết mịn) nhiều khả năng là lựa
chọn tốt hơn. 2.0 được chọn làm mặc định có lý do: nó phục hồi hầu hết độ mềm
nhìn thấy được trong khi vẫn nhỏ hơn và nhanh hơn nhiều so với đường per-dab
trên mọi tài liệu thử ở đây; một họa tiết mềm, tương phản thấp (mảng hồng má
"yanak") trông gần như giống hệt ở mọi N, kể cả 1.0, nên sự đánh đổi này chỉ
quan trọng với các brush mảnh/mờ như "golge", không phải họa tiết brush nói
chung.

Chọn `--brush-raster` khi kích thước file/tốc độ render quan trọng hơn độ
trung thực họa tiết chính xác từng pixel (một preview nhanh, một bản nhúng
web); ưu tiên đường per-dab `<use>` mặc định khi bản thân họa tiết mịn là điều
đáng giá và bạn không bị giới hạn kích thước/tốc độ. Điều này cũng ảnh hưởng
tới việc kết quả giữ vững thế nào khi phóng to hoặc in ở DPI cao — xem
[§ 7.4](#74-đánh-đổi-zoomkhả-năng-co-giãn-giữa-ba-đường-render).

Pattern rule `out/svg/raster/%.svg` làm điều tương tự cho bất kỳ dự án nào
(ví dụ `make out/svg/raster/Bandit.svg`), ghi vào `out/svg/raster/` bị
gitignore.

### 7.3 Vì sao đường fallback tốn kém khi *xem*

Không có Pillow, mỗi dab được stamp là một `<g transform="..."><rect .../></g>`
được mask bởi một `<mask>` dùng chung chứa một `<image>` (họa tiết brush) cộng
một `<feColorMatrix>` filter (xem [Định dạng file dự án Moho § 8.5](moho-project-file-format.md#85-kiểu-cọ)
để biết vì sao có filter đó).
Mọi phần tử tham chiếu một `mask` buộc một trình render tuân theo spec phải
render nội dung của chính mask vào một offscreen buffer, áp filter lên nó, rồi
dùng kết quả để gộp phần tử đó — ba bước thực sự, lặp lại một lần cho mỗi dab,
bất kể *văn bản* của file nhỏ đến đâu. Đây là lý do thời gian render trên
đường này bám theo số dab sát hơn nhiều so với việc bám theo kích thước file
hay độ phân giải pixel đầu ra. Nó cũng là lý do một số trình xem không mở nổi
một bản xuất nhiều brush trên đường này — nhiều trình giới hạn số thao tác
filter/mask đồng thời chúng sẽ thử, hoặc hết bộ nhớ khi giữ quá nhiều offscreen
buffer cùng lúc. Đường Pillow tránh tất cả điều này bằng cách tô màu lại một
lần, trong Python, thay vì một lần mỗi dab trong trình xem.

### 7.4 Đánh đổi zoom/khả năng co giãn giữa ba đường render

Mọi đường render giữ HÌNH HỌC thực của shape (path `d="..."` của nó, tức vị
trí và outline) là dữ liệu vector thật, ở mọi mức zoom, bất kể cài đặt brush.
Sự đánh đổi bàn ở trên (§ 7.1-7.3) cụ thể là về cách *họa tiết brush vẽ dọc
theo outline đó* được biểu diễn, và điều đó có hậu quả thật cho việc kết quả
giữ vững thế nào khi phóng to xa hơn nhiều kích thước nó được xuất/xem (một
cửa sổ trình xem ở zoom cao, một bản in ở DPI cao hơn nhiều độ phân giải màn
hình, v.v.):

| Đường render | Họa tiết brush là... | Hành vi khi zoom |
|---|---|---|
| `--brush-dir ""` (không brush) | Không có — nét đơn giản hoặc ribbon TaperedStrokeOutliner | Vẫn sắc nét hoàn hảo ở mọi zoom — nó 100% vector, không hề có raster. |
| Mặc định (Pillow per-dab `<use>`) | Một raster image nhỏ cho mỗi *dab* (gần bằng đường kính của chính dab, ví dụ 10-80px), dùng lại qua `<use>` | Xuống cấp muộn hơn nhiều / duyên dáng hơn: mỗi dab là một ảnh nhỏ đã gần kích thước hiển thị của nó, nên mức zoom thông thường hiếm khi vượt độ phân giải gốc của nó. Phóng đủ sâu vào BẤT KỲ một dab nào cuối cùng nó cũng mờ — bên dưới vẫn là một họa tiết raster — nhưng "đơn vị" bị mờ là nhỏ. |
| `--brush-raster` | MỘT raster image cho toàn bộ nét của *cả shape*, chụp ở `brush_raster_supersample`x kích thước pixel của nó (mặc định 2x) lúc xuất | Xuống cấp sớm hơn và thấy rõ hơn: toàn bộ nét dùng chung một bitmap độ phân giải cố định, nên phóng trình xem/bản in vượt độ phân giải đã chụp sẽ làm mờ/vỡ hạt toàn bộ nét cùng lúc, không chỉ chi tiết mịn bên trong. Đây là cái giá trực tiếp, dự kiến của việc gộp nhiều dab thành một ảnh (§ 7.2) — không phải bug. |

Tăng `--brush-raster-supersample` nâng trần độ phân giải trước khi điều này
xảy ra (§ 7.2), nhưng nó vẫn là một trần, không phải độc lập tỷ lệ — không có
giá trị nào của nó làm cho `--brush-raster` hoạt động như đầu ra vector thật
dưới zoom không giới hạn. Nếu một tài liệu cần được xem/in ở độ phân giải cao
hơn đáng kể kích thước canvas của chính nó (không chỉ xem nhanh ở gần 1:1), hãy
ưu tiên đường per-dab `<use>` mặc định, hoặc bỏ hẳn họa tiết brush bằng
`--brush-dir ""`, thay vì `--brush-raster`.

## 8. Giới hạn đã biết

Việc xuất của công cụ này là một tái dựng nỗ lực tối đa từ một định dạng file
không có tài liệu, được kiểm chứng thực nghiệm với render thật của Moho khi có
thể. Một số thứ là chính xác và đã xác nhận; số khác là xấp xỉ. Trước khi dựa
vào một kết quả bất thường, hãy kiểm tra phần KNOWN GAPS trong module
docstring, nó liệt kê (kèm lập luận cho từng mục):

- Chế độ kết hợp shape boolean `combo_mode == 2` chưa được reverse-engineer.
- Vị trí tâm/bán kính gradient là xấp xỉ, không khớp từng pixel.
- Độ giảm dần trọng số bind bone mềm chưa được kiểm chứng cho các trường hợp
  nhiều hơn một bone có ảnh hưởng đáng kể tại một điểm.
- `PatchLayer` chưa được mô hình hóa (quan sát thấy không tạo hình học nhìn
  thấy được trong mọi tài liệu tham chiếu cho tới nay).
- Physics, IK, và layer effects/shadows bị bỏ qua (một bản xuất phẳng một
  khung hình không bị ảnh hưởng bởi bất kỳ thứ nào trong số đó).
- Nét brush có họa tiết là một xấp xỉ với thêm vài đơn giản hóa nữa — xem
  [§ 7](#7-họa-tiết-cọ-brush) và module docstring.
