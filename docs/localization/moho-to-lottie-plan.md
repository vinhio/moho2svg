# Kế hoạch triển khai Moho sang Lottie

> Bản dịch tiếng Việt của `docs/moho-to-lottie-plan.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

> **Dành cho agent tự động:** KỸ NĂNG CON BẮT BUỘC: dùng superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để triển khai kế hoạch này theo từng nhiệm vụ. Các bước dùng cú pháp checkbox (`- [ ]`) để theo dõi.

**Mục tiêu:** Thêm `moho2lottie.py`, một exporter thứ hai ghi toàn bộ một tài liệu Moho thành một file Lottie JSON hoạt ảnh chạy được trong lottie-web.

**Kiến trúc:** Dùng lại nguyên vẹn pipeline hình học của `moho2svg.py`. Hai bổ sung nhỏ cho nó — một trình dựng path Bezier đặt bên cạnh `build_path_d`, và một bước duyệt cây dùng chung mà cả hai exporter cùng tiêu thụ — rồi một writer mới bake mọi biến dạng vào vị trí đỉnh theo pixel canvas, để mọi Lottie layer giữ một transform đơn vị (identity).

**Công nghệ:** Python 3, chỉ thư viện chuẩn. `jsonschema` và Pillow là tùy chọn và không bao giờ được trở thành bắt buộc. Không có test framework: việc xác minh là các check script trong `tools/` được điều khiển bởi `make`, khớp với cách repo này tự xác minh.

**Spec:** [`moho-to-lottie-design.md`](moho-to-lottie-design.md) — đọc nó trước Nhiệm vụ 1. Kế hoạch này triển khai thiết kế đó và không nhắc lại lập luận của nó.

---

## Tái cấu trúc Makefile (2026-08-15)

Sau khi kế hoạch này hoàn thành, Makefile được tái cấu trúc. Các target tổng
hợp `gen`, `gen-med`, `gen-fast`, `gen-raster` và `gen-lottie` không còn tồn
tại, và `make styles.brushes` cũng bị xóa (họa tiết brush giờ được sao chép
bằng `cp -R /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/`
thay vì symlink). Đầu ra dời về dưới `out/`: `svg/` → `out/svg/ori/`,
`svg-med/` → `out/svg/med/`, `svg-fast/` → `out/svg/fast/`, `svg-raster/` →
`out/svg/raster/`, `lottie-out/` → `out/lottie/`; không gì dưới `out/` được
track. Mọi bản xuất được dựng bằng pattern rule với file đầu ra làm target
(`make out/svg/ori/Bandit.svg`), `make svg-all` và `make lottie-all` bao phủ
mọi dự án dưới `moho/`, `make check-lottie` phụ thuộc vào ba bản xuất mẫu, và
`make format/moho/TÊN` ghi `moho/TÊN.json`. Các lệnh `make gen` lịch sử trong
các bước nhiệm vụ và nhật ký chạy bên dưới nói về Makefile cũ và được giữ làm
bản ghi.

---

## Tiến độ

Bảng này là nơi duy nhất để đọc trạng thái tổng thể. Các bước của từng nhiệm vụ
mang checkbox `- [ ]` ở phía dưới.

**Cách cập nhật nó.** Một nhiệm vụ chỉ trở thành `DONE` khi **commit cuối cùng
của nó đã hạ cánh** và check đã nêu của nó đã qua — không phải khi code được
viết. Hãy tick checkbox bước của nhiệm vụ khi làm, rồi lật dòng và ghi lại
commit. Bất cứ thứ gì đã bắt đầu mà chưa xong là `IN PROGRESS`, và dòng của nó
cho biết nó dừng ở bước nào, để người đọc biết nơi tiếp tục.

| # | Hạng mục công việc | Trạng thái | Commit |
|---|---|---|---|
| P1 | Thử nghiệm khả thi — độ ổn định đỉnh path, tách chuyển động, đếm tính năng | **DONE** | *(script dùng một lần, không commit)* |
| P2 | Sửa: tải các curve point định dạng `1021` bỏ sót weight và offset | **DONE** | `be27b10` |
| P3 | Sửa: đặt lại cache của `Channel` khi một tài liệu được parse | **DONE** | `5c4b8c3` |
| P4 | Tài liệu thiết kế | **DONE** | `87abe40` |
| P5 | Kế hoạch này | **DONE** | `496f35c` |
| 1 | Một trình dựng path Bezier bên cạnh trình dựng SVG | **DONE** | `a91df9f` |
| 2 | Một bước duyệt cây dùng chung | **DONE** | `a81a6cb` |
| 3 | Một file Lottie với một frame tĩnh | **DONE** | `4189275` |
| 4 | Path keyframe trên toàn dải frame | **DONE** | `4b31129` |
| 5 | Gradient | **DONE** | `e1aa6d1` |
| 6 | Masking | **DONE** | `62d497a` |
| 7 | Switch layer | **DONE** | `4afc76c` |
| 8 | Cảnh báo, make target và xác thực schema tùy chọn | **DONE** | `4d8b1be` |

Hai mục không thể được chốt bởi bất kỳ nhiệm vụ nào ở trên, vì cả hai đều cần một
Lottie player thật — thứ không phần nào của dự án này từng dựng, cài, hay chạy.
Chúng được mô tả ở cuối tài liệu này và vẫn mở cho đến khi ai đó tải đầu ra
trong lottie-web:

| # | Câu hỏi mở | Trạng thái |
|---|---|---|
| Q1 | `op` của Lottie có loại trừ không? `LottieExporter.export` giả định `end_frame + 1` | OPEN |
| Q2 | Khiếm khuyết thứ tự kế thừa `masking == 2` của `Bandit.mohoproj` thấy rõ hơn hay kém hơn trong một Lottie player so với trong SVG? | OPEN |

(Q2 gốc - "một paint operator có áp dụng cho các shape mà writer định ý không"
- hóa ra đã được giải quyết THEO THIẾT KẾ, không phải bởi một player: xem ghi
chú của riêng Nhiệm vụ 8 và `moho-to-lottie-design.md` § 9 mục 2.)

---

## Ràng buộc toàn cục

- **Chỉ tiếng Anh** trong mọi file, comment, docstring, commit message và chuỗi in ra. Xem `.claude/ai/AGENTS.md`.
- **Không có dependency bên thứ ba bắt buộc mới.** `jsonschema` là tùy chọn theo cùng cách Pillow đã là: thử import, bỏ qua với một ghi chú in ra nếu vắng mặt.
- **Chỉ thư viện chuẩn** trong `moho2lottie.py` và mọi script trong `tools/`.
- **Kiểu commit:** câu mệnh lệnh đơn giản, khớp `git log`. Không phải Conventional Commits. Không ghi công cụ, không có trailer đồng tác giả AI.
- **Mọi tài liệu phải mang một docstring.** File mới, class mới, hàm mới, kể cả helper riêng. Khớp mật độ và giọng văn của `moho2svg.py`, thứ giải thích *vì sao* một hằng số là như vậy.
- **`make gen` phải giữ năm SVG được theo dõi byte-identical** sau mọi nhiệm vụ. Đây là cổng hồi quy của toàn bộ kế hoạch, không chỉ của Nhiệm vụ 2.
- **Không bao giờ thầm lặng bỏ qua một tính năng.** Bất cứ thứ gì không được xuất đều tăng một bộ đếm được in ra stderr ở cuối một lần xuất.
- Tọa độ được viết với 3 chữ số thập phân, khớp `f"{x:.3f}"` của `build_path_d`.

---

## Cấu trúc file

| File | Trách nhiệm |
|---|---|
| `moho2svg.py` (sửa) | Nhận thêm `build_path_bezier()` và `walk_render_tree()`. Không gì khác thay đổi; đầu ra của chính nó không được xê dịch một byte. |
| `moho2lottie.py` (tạo) | Writer Lottie và CLI của nó. Một file với các banner `# ==== SECTION ====`, phản chiếu cách `moho2svg.py` được tổ chức. |
| `tools/check_bezier_roundtrip.py` (tạo) | Chứng minh `build_path_bezier()` mô tả cùng một curve như `build_path_d()`. |
| `tools/check_lottie_geometry.py` (tạo) | Chứng minh một file Lottie được xuất vẽ cùng các tọa độ, cùng thứ tự, như writer SVG ở cùng một frame. |
| `Makefile` (sửa) | Thêm `gen-lottie`, `check-lottie`. |
| `.gitignore` (sửa) | Thêm `lottie-out/`. |

---

## Nhiệm vụ 1: Trình dựng path Bezier bên cạnh trình dựng SVG

**Trạng thái:** DONE — `check_bezier_roundtrip.py` qua trên cả 19 tài liệu mẫu; `make gen` để năm SVG tham chiếu byte-identical.

**Các file:**
- Sửa: `moho2svg.py` — thêm `build_path_bezier()` ngay sau `build_path_d()`
- Tạo: `tools/check_bezier_roundtrip.py`

**Giao diện:**
- Tiêu thụ: `PathTracer.trace(geometries, edges) -> list[TracedSegment]`, trong đó `TracedSegment` có `p0, c1, c2, p1, is_new_subpath, reversed, curve, segment`; `Vec2` có `.x`, `.y`, `.distance_to(other)`.
- Sinh ra: `build_path_bezier(geometries, edges, to_px, visible_only=False) -> list[dict]` — **một dict cho mỗi subpath**, mỗi cái `{"v": [[x, y], ...], "i": [[dx, dy], ...], "o": [[dx, dy], ...], "c": bool}`. Một shape có hai đường viền rời nhau trả về hai dict, và writer phát ra một phần tử Lottie `sh` cho mỗi dict.

- [x] **Bước 1: Viết check script dự kiến fail**

Tạo `tools/check_bezier_roundtrip.py`:

```python
#!/usr/bin/env python3
"""Check that build_path_bezier() describes the same curve as build_path_d().

Both are built from the same PathTracer output, so they must agree exactly.
This converts each emitted Lottie bezier back to absolute cubic control
points and compares them against the traced segments the SVG writer uses.

Exit status is 0 when every shape agrees, 1 otherwise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moho2svg import (Channel, Exporter, PathTracer, build_deform_chain,
                      build_path_bezier, load_document)

MOHO_DIR = "moho"
FRAMES = [0.0, 7.0, 23.0]

# build_path_bezier() rounds to 3 decimals, matching build_path_d()'s
# f"{x:.3f}", and its tangents are DIFFERENCES of two rounded values, so a
# rebuilt control point can be off by up to two half-ulps of 0.001.  The
# tolerance has to sit above that, or a correct implementation fails this
# check.  It is still tight enough to catch any real geometry mistake, which
# would be off by pixels, not by a thousandth of one.
TOLERANCE = 3e-3


def absolute_segments(bezier):
    """Rebuild absolute (p0, c1, c2, p1) tuples from one Lottie bezier dict.

    Lottie stores `i` and `o` relative to their own vertex, so a segment
    running from vertex k to vertex k+1 has control points v[k] + o[k] and
    v[k+1] + i[k+1].
    """
    v, tin, tout, closed = bezier["v"], bezier["i"], bezier["o"], bezier["c"]
    count = len(v) if closed else len(v) - 1
    out = []
    for k in range(count):
        nxt = (k + 1) % len(v)
        out.append((
            (v[k][0], v[k][1]),
            (v[k][0] + tout[k][0], v[k][1] + tout[k][1]),
            (v[nxt][0] + tin[nxt][0], v[nxt][1] + tin[nxt][1]),
            (v[nxt][0], v[nxt][1]),
        ))
    return out


def traced_segments(geometries, edges, to_px):
    """The same segments the SVG writer walks, mapped to pixels."""
    out = []
    for seg in PathTracer.trace(geometries, edges):
        pts = [to_px(p) for p in (seg.p0, seg.c1, seg.c2, seg.p1)]
        out.append(tuple((p.x, p.y) for p in pts))
    return out


def check_document(path):
    """Compare both builders over one document. Returns the failure count."""
    Channel.reset_cache()
    doc = load_document(path)
    failures = 0
    for frame in FRAMES:
        exp = Exporter(doc)
        for ancestors, layer in doc.vector_layers():
            exp._active_actions = exp._active_actions_along(ancestors, frame)
            exp._layer_scale = exp._full_chain_matrix(ancestors, layer, frame).uniform_scale() or 1.0
            geometries = exp._curve_geometries(layer.mesh, frame)
            chain = build_deform_chain(ancestors, layer, frame, exp)
            to_px = exp._deformed_pixel_mapper(chain, frame, layer)
            exp._active_actions = []
            for index, shape in enumerate(layer.mesh.shapes):
                if not shape.edges:
                    continue
                expected = traced_segments(geometries, shape.edges, to_px)
                got = []
                for bezier in build_path_bezier(geometries, shape.edges, to_px):
                    got.extend(absolute_segments(bezier))
                if len(got) != len(expected):
                    print(f"  {os.path.basename(path)} {layer.name} shape[{index}] "
                          f"frame {frame}: {len(got)} segments, expected {len(expected)}")
                    failures += 1
                    continue
                for a, b in zip(got, expected):
                    if any(abs(x - y) > TOLERANCE for pa, pb in zip(a, b)
                           for x, y in zip(pa, pb)):
                        print(f"  {os.path.basename(path)} {layer.name} "
                              f"shape[{index}] frame {frame}: coordinates differ")
                        failures += 1
                        break
    return failures


def main():
    targets = sys.argv[1:] or sorted(
        os.path.join(MOHO_DIR, f) for f in os.listdir(MOHO_DIR)
        if f.endswith((".mohoproj", ".animeproj"))
    )
    failures = 0
    for path in targets:
        failures += check_document(path)
        print(f"checked {os.path.basename(path)}")
    if failures:
        print(f"\nFAIL: {failures} shape(s) disagree")
        return 1
    print(f"\nOK: both path builders agree on every shape in {len(targets)} document(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Bước 2: Chạy nó để xác minh nó fail**

Chạy: `python3 tools/check_bezier_roundtrip.py moho/Bandit.mohoproj`
Dự kiến: FAIL với `ImportError: cannot import name 'build_path_bezier' from 'moho2svg'`

- [x] **Bước 3: Triển khai `build_path_bezier()`**

Thêm vào `moho2svg.py` ngay sau `build_path_d()`:

```python
def build_path_bezier(geometries: list[CurveGeometry], edges: Sequence[Edge],
                       to_px: Callable[[Vec2], Vec2],
                       visible_only: bool = False) -> list[dict]:
    """Build one shape's outline as Lottie bezier dicts - the Lottie
    counterpart of build_path_d().

    Returns ONE dict per subpath, because Lottie's `sh` shape element holds
    exactly one bezier: a shape whose outline falls into two disconnected
    runs becomes two `sh` elements in the same group.  build_path_d() writes
    the same break as a second "M" inside one `d` string.

    Lottie's `i` and `o` are the in/out tangents *relative to their own
    vertex*, so a segment leaving vertex k contributes `o[k] = c1 - p0` and
    the vertex it arrives at gets `i[k+1] = c2 - p1`.  A vertex shared by two
    segments therefore takes `o` from the outgoing segment and `i` from the
    incoming one.

    `visible_only` skips segments currently hidden by CurvePoint.segments_on,
    exactly as build_path_d() does, starting a fresh subpath after each gap.
    """
    traced = PathTracer.trace(geometries, edges)
    out: list[dict] = []
    current: Optional[dict] = None
    first: Optional[Vec2] = None
    last: Optional[Vec2] = None

    def close_current() -> None:
        """Finish the subpath being built, marking it closed when it returns
        to its own start.

        A closed Lottie bezier does not repeat the first vertex, so the
        duplicate endpoint is dropped - but its incoming tangent is the
        wrap-around segment's control point and must be carried onto the
        surviving first vertex before the drop, or the last curve of a closed
        shape flattens into a straight line.
        """
        nonlocal current
        if current is None:
            return
        if len(current["v"]) > 1 and first is not None and last is not None \
                and last.distance_to(first) < 1e-9:
            current["c"] = True
            current["i"][0] = current["i"][-1]     # carry the wrap-around tangent
            current["v"].pop()
            current["i"].pop()
            current["o"].pop()
        out.append(current)
        current = None

    for seg in traced:
        if visible_only and not geometries[seg.curve].segments[seg.segment].on:
            close_current()
            last = None
            continue
        if current is None or last is None or last.distance_to(seg.p0) > 1e-9:
            close_current()
            p0 = to_px(seg.p0)
            current = {"v": [[round(p0.x, 3), round(p0.y, 3)]],
                        "i": [[0.0, 0.0]], "o": [[0.0, 0.0]], "c": False}
            first = seg.p0
        p0, c1, c2, p1 = (to_px(seg.p0), to_px(seg.c1),
                           to_px(seg.c2), to_px(seg.p1))
        current["o"][-1] = [round(c1.x - p0.x, 3), round(c1.y - p0.y, 3)]
        current["v"].append([round(p1.x, 3), round(p1.y, 3)])
        current["i"].append([round(c2.x - p1.x, 3), round(c2.y - p1.y, 3)])
        current["o"].append([0.0, 0.0])
        last = seg.p1
    close_current()
    return out
```

Việc mang tangent quấn vòng bên trong `close_current` là dòng tinh tế duy nhất
trong toàn hàm. Bỏ đỉnh cuối lặp lại mà không có nó làm curve cuối của mọi shape
kín render thành một đường thẳng — một khiếm khuyết dễ bỏ sót trên một shape bo
tròn và rõ ràng trên một hình tròn.

- [x] **Bước 4: Chạy check để xác minh nó qua**

Chạy: `python3 tools/check_bezier_roundtrip.py`
Dự kiến: `OK: both path builders agree on every shape in 19 document(s)`

Nếu một shape kín fail ở segment đầu hoặc cuối của nó, việc mang tangent quấn
vòng trong `close_current` là sai — đó là nơi duy nhất hai trình dựng có thể
bất đồng một cách hợp pháp.

- [x] **Bước 5: Xác minh đầu ra SVG không xê dịch**

Chạy: `make gen && git diff --stat -- svg/`
Dự kiến: đầu ra rỗng.

- [x] **Bước 6: Commit**

```bash
git add moho2svg.py tools/check_bezier_roundtrip.py
git commit -m "Add a Lottie bezier path builder beside the SVG one"
```

---

## Nhiệm vụ 2: Một bước duyệt cây dùng chung

**Trạng thái:** DONE — xem ghi chú bên dưới về việc vì sao hình dạng đổi so với
phác thảo gốc của nhiệm vụ này, và đọc nó trước khi bắt đầu Nhiệm vụ 3.

**Các file:**
- Sửa: `moho2svg.py` — `Exporter.export_document` (closure `emit`) và một dataclass `RenderItem` cấp module mới cùng `walk_render_tree()`

**⚠ Giao diện đã đổi so với phác thảo gốc bên dưới — đọc cái này trước.**
Trong lúc tách bước duyệt, một mối nguy đúng đắn hiện ra: 8 trong số 201
container trong toàn kho mẫu có **không một hậu duệ nào có thể vẽ được**
(thấy được, không `edit_only`, và — với một `SwitchLayer` — là con đang hoạt
động), và Moho vẫn vẽ một container như thế thành một **`<g></g>` rỗng**. Bốn
trong năm tài liệu bị cổng byte-identical chứa một cái. Một luồng `RenderItem`
chỉ sinh ra các mesh layer thực sự sẽ không có cách nào báo hiệu "một container
rỗng đã ở đây", nên `export_document` không thể dựng lại cái `<g>` rỗng đó —
cổng sẽ fail trên 4 trong 5 tài liệu, chứ không qua một cách thầm lặng.

Cách sửa là làm cho `walk_render_tree` sinh ra một **event stream** nhỏ thay vì
một danh sách phẳng "một item cho mỗi mesh layer" — `"enter"` trước các con của
một container, `"mesh"` cho mỗi mesh layer vẽ được, `"exit"` sau đó — phản
chiếu cấu trúc ngoặc mà `emit()` đã có. `export_document` dựng lại lớp `<g>`
của nó (kể cả các lớp rỗng) bằng cách tiêu thụ stream này một cách đệ quy, dùng
một **iterator dùng chung duy nhất**: một lời gọi lồng đọc trực tiếp từ cùng
iterator qua `for item in it`, và trả về từ lời gọi đó để iterator đúng ở nơi
vòng lặp của chính người gọi tiếp tục — cách chuẩn để tiêu thụ một chuỗi khớp
ngoặc đã làm phẳng mà không dựng lại một stack bằng tay.

**Các consumer viết sau nhiệm vụ này (từ Nhiệm vụ 3 trở đi) phải lọc theo
`item.event == "mesh"`** — stream cũng chứa các event `"enter"`/`"exit"` không
mang `geometries`/`to_px` gì cả.

**Giao diện:**
- Tiêu thụ: mọi thứ `export_document` đã dùng — `Exporter._mask_sources`, `Layer.switch_active_child`, `Layer.local_matrix`, `build_deform_chain`, `Exporter._deformed_pixel_mapper`, `Exporter._curve_geometries`.
- Sinh ra:
  ```python
  @dataclass
  class RenderItem:
      event: str                              # "enter" | "mesh" | "exit"
      layer: Optional[Layer]                  # None only for "enter"/"exit" of the virtual root
      ancestors: tuple                        # root-first, ending in the enclosing container
      depth: int                              # len(ancestors) — true tree depth, NOT an SVG indent
      exempt: bool = False                    # masking in (1, 2), relative to the PARENT's mask
      mask_sources: Sequence = ()             # only non-empty on "enter"; this container's OWN group_mask contribution
      geometries: Optional[list] = None       # only set on "mesh"
      to_px: Optional[Callable] = None        # only set on "mesh"

  def walk_render_tree(exporter, frame, include_hidden=False) -> Iterator[RenderItem]
  ```
  Một `"mesh"` `RenderItem` được sinh ra với `exporter._active_actions` đã
  được đặt đúng ngữ cảnh Smart Bone, và ngữ cảnh đó **được giữ nguyên qua lần
  sinh ra** — chỉ bị xóa khi consumer xin item kế tiếp. Một consumer phải đánh
  giá xong các style channel của riêng layer đó trước khi tiến iterator.

- [x] **Bước 1: Chụp đầu ra hiện tại làm tham chiếu**

Thật sự chạy (repo này không có `git stash` nào trong hành trình; hãy copy thay
vì stash):
```bash
make gen && cp -R svg /tmp/svg-before
```
**Đã xác nhận.** `/tmp/svg-before` giữ năm SVG tham chiếu trước khi sửa của
nhiệm vụ này.

- [x] **Bước 2: Tách bước duyệt**

Đã chuyển thân của `emit` vào `walk()` lồng nhau của `walk_render_tree`, đổi
để sinh ra các event `RenderItem` thay vì dựng chuỗi SVG, đúng như mô tả trong
ghi chú "giao diện đã đổi" ở trên. Mọi quyết định được giữ nguyên chỗ và theo
thứ tự:

- cái bỏ qua `not layer.visible and not include_hidden`
- cái bỏ qua `layer.edit_only and not include_hidden`
- cái bỏ qua `active_child is not None and layer is not active_child`
- phép hợp `world.compose(layer.local_matrix(frame, self))`
- phép đệ quy vào `layer.is_container`

**Thứ tự set/clear `_active_actions` được giữ nguyên chính xác, theo cấu tạo**:
`exporter._active_actions = []` nằm về mặt văn bản SAU dòng
`yield RenderItem("mesh", ...)`, nên nó chỉ chạy khi generator được *tiếp tục*
— tức là, khi consumer đã xử lý xong item đó và xin item kế tiếp. Điều này tái
hiện thứ tự của code gốc (clear xảy ra ngay sau khi `_render_mesh` xong, trước
layer kế tiếp) mà generator không cần biết gì về việc consumer đã làm gì với
item. Xem `moho-export-pipeline.md` § 9.3 về việc vì sao thứ tự này chịu lực
(load-bearing) chứ không phải ngẫu nhiên.

- [x] **Bước 3: Viết lại `export_document` như một consumer**

`export_document` giữ lớp `<g>`, việc phát mask và xử lý `--flat` của nó, trong
một closure mới `render_scope(enter_item, pad_depth)` tiêu thụ iterator dùng
chung một cách đệ quy. `pad_depth` được theo dõi tách khỏi `RenderItem.depth`,
vì việc đệ quy của riêng một container lồng có thật sự tăng thụt lề SVG hay
không phụ thuộc `nested_groups`/`member_clip` — một lựa chọn trình bày mà
`walk_render_tree` không có ý kiến.

- [x] **Bước 4: Xác minh đầu ra byte-identical**

Đã chạy: `make gen && git diff --stat -- svg/ && diff -r svg /tmp/svg-before`.
**Cả hai không sinh ra đầu ra nào** — đã xác nhận byte-identical trên cả năm
tài liệu bị cổng, kể cả `AddBone`, `SketchBone` và `WhatIsBone`, ba trong bốn
tài liệu bị cổng chứa một container rỗng.

Đã đi xa hơn cổng của chính kế hoạch: xuất cả **19** tài liệu mẫu với
`--combined` dưới cả code trước-tách (checkout qua một `git worktree` dùng một
lần tại commit của Nhiệm vụ 1) lẫn code sau-tách, và diff hai tập đầu ra.
**Byte-identical trên cả 19**, kể cả 5 tài liệu không bị cổng thêm cũng chứa
một container rỗng (`BoneStrengthTool.animeproj` ×2, `ReparentBone.animeproj`,
`SelectandReparentBoneTool.animeproj`, instance thứ hai của
`SketchBone.animeproj`). Đây là bằng chứng mạnh hơn những gì kế hoạch yêu cầu,
cụ thể vì mối nguy container-rỗng không phải thứ kế hoạch lường trước.

- [x] **Bước 5: Xác minh mọi tài liệu vẫn xuất được**

Đã chạy:
```bash
for f in moho/*.mohoproj moho/*.animeproj; do
  python3 moho2svg.py "$f" --combined /tmp/out.svg --brush-dir "" >/dev/null || echo "FAILED $f"
done
```
Không có dòng `FAILED` nào.

- [x] **Bước 6: Commit**

```bash
git add moho2svg.py
git commit -m "Extract the layer tree walk so a second exporter can reuse it"
```

---

## Nhiệm vụ 3: Một file Lottie với một frame tĩnh

**Trạng thái:** DONE — với hai lần mở rộng phạm vi được thấy là cần thiết trong
lúc triển khai, cả hai đều không có trong phác thảo gốc bên dưới. Đọc ghi chú
trước Bước 3.

**⚠ Phạm vi đã được mở rộng vượt phác thảo gốc của nhiệm vụ này — đọc cái này
trước.** Phác thảo code của chính kế hoạch cho `_build_shapes` hóa ra sai theo
cách sẽ render sai ĐA SỐ shape có nét viền, không phải một trường hợp rìa:

1. **Nét viền làm thon (tapered stroke).** Đã đo: **1.065 trong 1.615 shape có
   nét viền (66%)** trong toàn kho mẫu có bề rộng thay đổi dọc theo chiều dài.
   Tài liệu thiết kế liệt kê nét viền làm thon là trong-phạm-vi của v1 ("đã
   chuyển những cái này thành một đường viền được tô, nên chúng đến như hình
   học thường"), nhưng fallback `_mean_point_width` của phác thảo
   (`widths[0] if untapered else 1.0`) sẽ vẽ một nét đều trơn ở bề rộng SAI cho
   hai phần ba mọi shape có nét viền — thầm lặng, không cảnh báo, mâu thuẫn
   Ràng buộc toàn cục của chính kế hoạch này. Đã sửa bằng cách thêm
   `TaperedStrokeOutliner.build_bezier()` (một anh em Lottie-native của `build()`
   hiện chỉ-có-SVG), thứ dùng lại kỹ thuật lấy mẫu offset-curve của chính
   `build()` nhưng viết mỗi đỉnh với ZERO tangent (một polyline, khớp các
   segment SVG đường thẳng của chính `build()` ở cùng mật độ mẫu) và xấp xỉ
   cung SVG nắp-tròn của `build()` bằng `cap_segments` segment thẳng (định dạng
   bezier của Lottie không có primitive cung). Bản thân
   `TaperedStrokeOutliner.build()` và `_outline_one_run()` KHÔNG BỊ ĐỘNG — chỉ
   `_traced_runs()` được tách khỏi `build()` (một phép chuyển nguyên văn, bảo
   toàn hành vi: gom dữ liệu thuần túy, không định dạng float hay logic dành
   riêng cho SVG) để cả hai writer gom các run giống hệt nhau mà không nhân đôi
   phần đó. Đã xác minh: `make gen` vẫn byte-identical
   (`Bandit.svg`/`ReparentBone.svg` luyện 93/78 phần tử taper outline giữa
   chúng), và `build_bezier()` sinh ra đầu ra hai-vòng đúng cho cả trường hợp
   vòng kín lẫn trường hợp capsule hở, được kiểm trực tiếp trên các shape thật
   trong `SketchBone.animeproj`.

2. **Thứ tự phần tử shape là một câu hỏi mở thật, không phải một lựa chọn định
   dạng.** Phác thảo đặt các phần tử "sh" của phần tô một shape, một "fl", các
   phần tử "sh" của nét viền, và một "st"/"fl" thứ hai tất cả trong MỘT group
   Lottie. Việc một paint operator trong mảng `it` của Lottie chỉ áp dụng cho
   các anh em "sh" ĐỨNG NGAY TRƯỚC nó hay cho TẤT CẢ chúng được ghi rõ là
   **chưa xác minh** — [`lottie-and-thorvg.md`](lottie-and-thorvg.md) mục 6.4
   nói quy tắc thứ tự này không nằm trong schema. Đoán sai ở đây nghĩa là các
   paint operator phần tô và nét viền của một shape lây chéo nhau (ví dụ nét
   của nét viền cũng tô cả path của riêng phần tô). Đã né hoàn toàn bằng cách
   cho mỗi shape lên tới HAI group Lottie RIÊNG BIỆT — một cho phần tô, một cho
   nét viền — vì một paint operator được phạm vi hóa một cách không mơ hồ trong
   group RIÊNG của nó. Group nét viền được liệt kê trước (Lottie, như
   Moho/SVG, sơn các mục trước lên trên), khớp thứ tự sơn tô-dưới/viền-trên
   của chính `_render_shape`.

Cũng được thêm, không có trong phác thảo gốc: một tham số `close: bool = True`
trên `build_path_bezier()` (Nhiệm vụ 1), cần vì một nét trơn KHÔNG được đóng
path của nó như cách phần tô làm — xem docstring của chính `build_path_d()` về
việc vì sao chính exporter của Moho cũng không bao giờ đóng một path nét viền —
và một bộ đếm cảnh báo `"gradient"`, vì các phần tô `SS_Gradient2` được vẽ như
một màu phẳng cho đến Nhiệm vụ 5 và Ràng buộc toàn cục của chính kế hoạch cấm
một khoảng trống thầm lặng, không đếm.

**Các file:**
- Sửa: `moho2svg.py` — `Document.__init__`/`.from_raw` (`fps`/`start_frame`/`end_frame`), `build_path_bezier` (tham số `close` mới), `TaperedStrokeOutliner` (`_traced_runs` được tách, `build_bezier`/`_sample_offsets`/`_polygon_bezier`/`_arc_points`/`_outline_one_run_bezier` được thêm)
- Tạo: `moho2lottie.py`

**Giao diện:**
- Tiêu thụ: `walk_render_tree` và `build_path_bezier` từ Nhiệm vụ 1 và 2; `Color.from_raw`, `ResolvedStyle.line_cap_name`, `Exporter._stroke_width_px`, `Exporter.tapered_outliner.build_bezier`, `Shape.has_fill`/`.has_outline`/`.combo_mode`/`.style`/`.edges`.
- Sinh ra:
  ```python
  class LottieExporter:
      def __init__(self, document: Document, settings: RenderSettings = None)
      def export(self, frames: Sequence[float]) -> dict
  ```
  Một danh sách `frames` một phần tử sinh ra một ảnh tĩnh; Nhiệm vụ 4 truyền
  toàn dải.

- [x] **Bước 1: Thêm ba accessor của document**

Trong `moho2svg.py`, `Document.__init__` và `Document.from_raw` hiện chỉ giữ
`width`, `height`, `layers`, `styles`, `format_version`. Thêm `fps`,
`start_frame` và `end_frame`, đọc từ cùng dict `project_data`:

```python
        doc = cls(pd["width"], pd["height"], layers, styles, raw.get("version"),
                  fps=pd.get("fps", 24.0),
                  start_frame=pd.get("start_frame", 0),
                  end_frame=pd.get("end_frame", 0))
```

Ghi tài liệu chúng: `fps` là tốc độ phát lại, `start_frame`/`end_frame` là dải
render riêng của tài liệu theo số frame tuyệt đối, và cả hai đều bao gồm về
phía Moho.

- [x] **Bước 2: Viết check dự kiến fail**

Chạy: `python3 moho2lottie.py moho/Bandit.mohoproj --out /tmp/bandit.json --frame 25`
Dự kiến: FAIL với `No such file or directory: 'moho2lottie.py'`

- [x] **Bước 3: Viết `moho2lottie.py`**

Cấu trúc nó với cùng kiểu banner mà `moho2svg.py` dùng:

```python
#!/usr/bin/env python3
"""Export Moho vector artwork to a Lottie JSON animation.

Reuses moho2svg.py's geometry pipeline in full: the same document model, the
same Bezier reconstruction, the same path tracing, the same bone deformation.
Only the output stage differs.

Every deformation is BAKED into canvas-pixel vertex positions, so every Lottie
layer carries an identity transform and no affine matrix is ever decomposed
into Lottie's anchor/position/scale/rotation/skew form.  See
docs/moho-to-lottie-design.md for why, and for what that costs in file size.
"""
```

Writer, theo thứ tự:

```python
LOTTIE_VERSION = "5.7.0"


class LottieExporter:
    """Builds a Lottie document from a Moho Document.

    Stateful in the same way Exporter is: it holds a per-export warning
    counter and reuses one Exporter for geometry.  Construct one per export
    call, never share across concurrent exports.
    """

    def __init__(self, document, settings=None):
        self.document = document
        self.exporter = Exporter(document, settings)
        self.warnings = Counter()

    def export(self, frames):
        """Return the Lottie document as a plain dict.

        `frames` is every frame to sample, in ascending order.  A single
        frame produces static paths; several produce path keyframes.
        """
        layers = self._build_layers(frames)
        return {
            "v": LOTTIE_VERSION,
            "fr": float(self.document.fps),
            "ip": float(self.document.start_frame),
            # Moho's end_frame is inclusive, Lottie's op is the first frame
            # NOT shown - see docs/moho-to-lottie-design.md section 9 item 1,
            # this is an inference and is on the list to confirm.
            "op": float(self.document.end_frame + 1),
            "w": int(self.document.width),
            "h": int(self.document.height),
            "assets": [],
            "layers": layers,
        }
```

Việc dựng layer, cho nhiệm vụ này, lấy mẫu một frame và phát các path tĩnh:

```python
    def _build_layers(self, frames):
        """One Lottie shape layer per Moho mesh layer, in Lottie draw order.

        walk_render_tree yields an EVENT STREAM ("enter"/"mesh"/"exit"), not
        one item per mesh layer - see Task 2's note on why. Only "mesh"
        events carry geometries/to_px; "enter"/"exit" exist purely so a
        consumer that needs Moho's nested <g> structure (export_document)
        can reconstruct it, including empty containers. This writer flattens
        everything anyway (every layer gets an identity transform), so it
        simply ignores "enter"/"exit" and keeps only "mesh" events.

        Moho draws its layer list back to front, which is the order
        walk_render_tree yields "mesh" events in.  Lottie draws the FIRST
        layer in the list on top, so the finished list is reversed.  This is
        the single easiest thing in the whole writer to get wrong without
        noticing: the artwork still looks right, just with the wrong parts
        in front.
        """
        collected = []
        for item in walk_render_tree(self.exporter, frames[0]):
            if item.event != "mesh":
                continue
            shapes = self._build_shapes(item, frames)
            if shapes:
                collected.append(self._shape_layer(item.layer.name, shapes))
        collected.reverse()                  # Moho back-to-front -> Lottie front-to-back
        for index, layer in enumerate(collected, start=1):
            layer["ind"] = index
        return collected

    def _shape_layer(self, name, shapes):
        """A Lottie shape layer with an identity transform.

        Identity is correct because the geometry is already baked into canvas
        pixels, which is also Lottie's own coordinate system: pixels, y down,
        origin at the top left.
        """
        return {
            "ty": 4, "nm": name, "ks": identity_transform(),
            "ao": 0, "shapes": shapes,
            "ip": float(self.document.start_frame),
            "op": float(self.document.end_frame + 1),
            "st": 0.0,
        }
```

`identity_transform()` là một hàm, không phải một hằng số module, để không hai
layer nào bao giờ dùng chung một dict có thể thay đổi:

```python
def identity_transform():
    """Lottie's neutral transform: no anchor, no move, no rotation, full size
    and full opacity."""
    return {"a": {"a": 0, "k": [0, 0]}, "p": {"a": 0, "k": [0, 0]},
            "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0},
            "o": {"a": 0, "k": 100}}
```

Việc dựng theo-shape giải quyết style theo cùng cách
`ShapeGroupRenderer._render_shape` làm, để cả hai exporter đọc màu và bề rộng
giống hệt nhau:

```python
    def _build_shapes(self, item, frames):
        """Every Moho shape of one layer, as Lottie group elements."""
        out = []
        exp, frame = self.exporter, frames[0]
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            if shape.combo_mode not in (0, None):
                self.warnings["combo_mode"] += 1
            if shape.style.brush_name:
                self.warnings["brush"] += 1
            beziers = build_path_bezier(item.geometries, shape.edges, item.to_px)
            if not beziers:
                continue
            elements = [{"ty": "sh", "ks": {"a": 0, "k": b}} for b in beziers]
            if shape.has_fill:
                color = Color.from_raw(exp.eval(shape.style.fill_color, frame))
                elements.append({"ty": "fl",
                                  "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                  "o": {"a": 0, "k": color.a * 100}})
            if shape.has_outline:
                width = exp._stroke_width_px(
                    exp.eval(shape.style.line_width, frame),
                    self._mean_point_width(item, shape, frame))
                color = Color.from_raw(exp.eval(shape.style.line_color, frame))
                elements.append({"ty": "st",
                                  "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                  "o": {"a": 0, "k": color.a * 100},
                                  "w": {"a": 0, "k": width},
                                  "lc": LINE_CAPS.get(shape.style.line_caps, 2),
                                  "lj": 2})
            elements.append({"ty": "tr", **identity_transform()})
            out.append({"ty": "gr", "nm": shape.name or "", "it": elements})
        return out
```

`LINE_CAPS` ánh xạ chuỗi mà `ResolvedStyle.line_cap_name()` đã trả về — cùng
giá trị writer SVG đặt trong `stroke-linecap` — lên số nguyên `lc` của Lottie:
`{"butt": 1, "round": 2, "square": 3}`. Suy ra nó từ `line_cap_name()` thay vì
từ int `line_caps` thô nghĩa là hai exporter không thể trôi xa nhau.

`_mean_point_width` phản chiếu việc tra bề rộng mà `ShapeGroupRenderer` làm cho
các edge point của chính shape, để stroke width nạp vào `_stroke_width_px` đúng
là cái writer SVG sẽ dùng.

Các import cần ở đầu file: `argparse`, `json`, `sys`, `Counter` từ
`collections`, và từ `moho2svg` — `Color`, `Exporter`, `RenderSettings`,
`build_path_bezier`, `load_document`, `walk_render_tree`.

CLI nhận `project`, `--out`, `--frame`, và `--include-hidden`, parse bằng
`argparse`, và ghi `json.dump(..., separators=(",", ":"))`.

- [x] **Bước 4: Chạy nó**

Chạy: `python3 moho2lottie.py moho/Bandit.mohoproj --out /tmp/bandit.json --frame 25`
Dự kiến: ghi file và in kích thước của nó cùng tóm tắt cảnh báo.

- [x] **Bước 5: Kiểm tra sơ bộ cấu trúc**

Chạy:
```bash
python3 -c "
import json; d=json.load(open('/tmp/bandit.json'))
print('fr',d['fr'],'ip',d['ip'],'op',d['op'],'w',d['w'],'h',d['h'])
print('layers',len(d['layers']))
print('first layer name', d['layers'][0]['nm'])
"
```
Dự kiến: `fr 24.0 ip 25.0 op 128.0 w 1920 h 1080`, một số layer khác không, và
tên layer đầu là layer **ở trước cùng** trong Moho, không phải ở sau cùng.

- [x] **Bước 6: Commit**

```bash
git add moho2lottie.py moho2svg.py
git commit -m "Write a static Lottie frame from a Moho document"
```

---

## Nhiệm vụ 4: Path keyframe trên toàn dải frame

**Trạng thái:** DONE — hai bug thật được tìm thấy và sửa trong lúc triển khai
nhiệm vụ này, cộng một phép đo trước đó (từ ghi chú hoàn thành của chính Nhiệm
vụ 3) được thấy là **sai** và được đính chính bên dưới. Đọc cả ba trước khi
đụng vào code này lần nữa.

**⚠ Bug 1 (thật, nghiêm trọng): `to_px()` đọc trạng thái exporter một cách
LAZY, tại thời điểm gọi, không phải tại thời điểm tạo closure.** Cài đặt đầu
tiên của `_build_layers` duyệt mọi frame trước, gom một `RenderItem` cho mỗi
cặp (layer, frame) vào một dict, và chỉ sau đó mới lặp lại qua chúng gọi
`.to_px()`/`build_path_bezier()`. Điều này sai: khóa cache của
`Exporter._skin_data` là `(bone_layer, frame, tuple(self._active_actions))`,
được đọc đúng lúc `to_px(p)` thật sự chạy, không được nướng vào closure khi
`walk_render_tree` dựng nó. Đến lúc lượt thứ hai chạy, `exporter._active_actions`
giữ bất cứ thứ gì frame/layer CUỐI CÙNG được xử lý để lại — mọi lời gọi hình
học thầm lặng dùng ngữ cảnh Smart Bone SAI. `tools/check_lottie_geometry.py`
bắt được cái này ngay lập tức: tọa độ lệch hàng trăm pixel (ví dụ x=805.9 dự
kiến, x=-287.5 nhận được), không phải một chênh lệch cỡ làm tròn. **Đã sửa**
bằng cách tái cấu trúc để mọi lời gọi `to_px()`/`exp.eval()` xảy ra đồng bộ,
bên trong chính vòng lặp `for item in walk_render_tree(...)` đã sinh ra `item`
- xem docstring của `_accumulate_frame`. Đây là sự thật đúng đắn quan trọng
nhất về file này: **không bao giờ giữ một `RenderItem` quá lúc xin
`walk_render_tree` cho item kế tiếp của nó.**

**⚠ Bug 2 (thật, của tôi): trộn lẫn "shape này có làm thon không" với
"`outline_kind` của nó có == 'stroke' không".** `outline_kind` của một shape có
cọ *luôn* là `"stroke"` (fallback cọ - xem `_new_accumulator`), kể cả khi bề
rộng của nó thật sự thay đổi dọc theo chiều dài. Một check nhất quán theo-frame
sớm so sánh độ làm-thon *thực tế* của mỗi frame với `outline_kind == "stroke"`
thay vì với cờ tapered *đã lưu*, nên nó gắn cờ mọi shape vừa cọ vừa làm thon là
"đã thay đổi" ngay ở frame thứ hai của nó. **12 trong 19 tài liệu mẫu báo lỗi ở
lần chạy đầu** - AddBone, AnglePositionScale, BoneParenting, ControlBones,
IK-FK, IndependentAngle, MaximumIKStrethching, OffsetBoneTool, SketchBone,
TargetBone, WhatIsBone (một cái nữa, giữa danh sách, không liệt kê lại để tránh
lỗi chép lại - xem toàn bộ đầu ra lần chạy đầu trong bản ghi phiên). **Đã sửa**
bằng cách lưu boolean `tapered` thô trong accumulator và so sánh với *cái đó*,
độc lập với `outline_kind`.

**⚠ Đính chính ghi chú hoàn thành của chính Nhiệm vụ 3: phép đo "6 trong 63
layer thay đổi tỷ lệ 21%" là SAI.** Nó gom các mẫu tỷ lệ theo `layer.name`,
trộn lẫn các layer khác nhau dùng chung một tên - `WhatIsBone.animeproj` có ba
layer được mô hình hóa riêng đều tên "goz-sol", mỗi cái có tỷ lệ hằng RIÊNG
của nó (1.0, 0.79, 1.0), trông như một layer có tỷ lệ thay đổi theo thời gian.
Đã đo lại khóa theo ĐỊNH DANH layer: **0 trong 103 layer của
`WhatIsBone.animeproj`, 0 trong 21 của `Bandit.mohoproj`, 0 trong 86 của
`SketchBone.animeproj` thật sự thay đổi** trên toàn dải frame riêng của chúng.
Bộ máy `_scalar_property`/stroke-width theo-frame mà "phát hiện" này thúc đẩy
**được giữ dù sao** - một bone có tỷ lệ hoạt ảnh thật sự là một khả năng thật
của Moho, không phải một trường hợp rìa bịa ra, và nhánh tĩnh đã phủ mọi thứ
thật sự quan sát được trong kho này - nhưng khẳng định của chính docstring được
sửa để nói như vậy, không lặp lại con số sai.

**Cũng được tìm thấy, không phải một bug: `SketchBone.animeproj` chưa thể xuất
toàn dải frame của nó.** Layer `agiz` (miệng) của nó là một `SwitchLayer` có
con đang hoạt động thay đổi suốt hoạt ảnh (lip sync), nên TẬP các layer vẽ được
tự nó khác nhau theo từng frame - đúng trường hợp docstring của chính
`_build_layers` đã lường trước và đặt tên là **việc của Nhiệm vụ 7**. Exporter
nâng một `ValueError` rõ ràng nêu tên layer thay vì thầm lặng tạo ra một file
sai. **18 trong 19 tài liệu mẫu xuất thành công toàn dải của chúng;
`SketchBone.animeproj` dự kiến bắt đầu hoạt động khi Nhiệm vụ 7 hạ cánh**, và
không bị ép sửa ở đây.

**Các file:**
- Sửa: `moho2lottie.py` — `_build_layers` được tái cấu trúc quanh việc tích lũy theo-frame háo hức (`_accumulate_frame`, `_new_accumulator`, `_finalize_shapes`, `_finalize_outline_group`), cộng `_path_property`, `_scalar_property`, `_sh_elements`, `_assert_stable`
- Tạo: `tools/check_lottie_geometry.py`

**Giao diện:**
- Sinh ra: `LottieExporter.export(frames)` giờ phát `{"a": 1, "k": [...]}` cho bất kỳ path nào (hoặc, với bề rộng của một nét trơn, bất kỳ scalar nào) có giá trị chuyển động, và giữ `{"a": 0, "k": ...}` cho cái không chuyển động.
- Dict accumulator được dựng bởi `_new_accumulator` (một cái cho mỗi shape, khóa theo vị trí trong `Mesh.shapes` — ổn định qua các frame) mang: `name`, `has_fill`, `fill_color`, `fill_per_frame`, `outline_kind` (`None`/`"taper"`/`"stroke"`), `tapered` (boolean THÔ — xem Bug 2 ở trên), `line_width`, `outline_color`, `outline_cap`, `outline_per_frame`, `outline_width_per_frame`.

- [x] **Bước 1: Viết check script dự kiến fail**

Tạo `tools/check_lottie_geometry.py`. Nó đọc một file Lottie đã phát ra, lấy
mọi giá trị path tại frame N, và so nó với `build_path_bezier` chạy trực tiếp
tại frame N:

```python
#!/usr/bin/env python3
"""Check that an emitted Lottie file holds the same geometry, in the same
order, that the SVG writer draws at the same frame.

This needs no Lottie player and no third-party package.  It also catches a
reversed layer order, because it compares shapes in emitted order.

Usage: check_lottie_geometry.py <project> <lottie.json> [frame ...]
Exit status is 0 when every shape at every checked frame agrees.
"""
```

Với mỗi frame được kiểm, nó phải:

1. duyệt tài liệu bằng `walk_render_tree(exporter, frame)`, gom bezier của mọi
   shape, và **đảo thứ tự layer** theo cùng cách writer làm;
2. duyệt `layers[*].shapes[*].it[*]` của file đã phát, chọn các phần tử
   `ty == "sh"`, lấy `k` tĩnh hoặc keyframe có `t` bằng frame;
3. so `v`, `i`, `o` và `c` từng phần tử với dung sai `3e-3` — cả hai phía đến
   từ `build_path_bezier`, nên chúng được làm tròn cùng cách, nhưng giữ cùng
   dung sai như `check_bezier_roundtrip.py` để hai script không thể bất đồng về
   "bằng" nghĩa là gì;
4. in tên layer, chỉ số shape và frame của mọi bất đồng.

Cũng được dựng với các cờ `--require-gradients`/`--require-masks`, trước Nhiệm
vụ 5/6, vì bộ máy duyệt-frame của chính script là giống hệt - hiện chúng chỉ
kiểm file phát ra có chứa một phần tử `"gf"` hoặc `hasMask`/`masksProperties`
khi tài liệu nguồn có một cái, tức là chúng là một LỜI NHẮC rằng các nhiệm vụ
đó chưa xong, không phải một khẳng định rằng chúng đã xong.

- [x] **Bước 2: Chạy nó để xác minh nó fail**

Chạy với file một-frame của Nhiệm vụ 3: FAILED như dự kiến, trên mọi shape
chuyển động - đã xác nhận chính check script hoạt động trước khi Bước 3 làm nó
qua vì đúng lý do.

- [x] **Bước 3: Phát keyframe**

Trong `_build_shapes`, dựng danh sách bezier của mỗi shape **một lần mỗi frame**
và so sánh. Viết lại phần tử path thành:

```python
    def _path_property(self, per_frame, frames):
        """A Lottie path property: static when the geometry never moves,
        keyframed otherwise.

        Writing an unmoving shape once instead of once per frame is what keeps
        the file in single-digit megabytes rather than hundreds - measured at
        293 MB versus about 10 MB across this repository's sample documents.
        """
        if all(b == per_frame[0] for b in per_frame[1:]):
            return {"a": 0, "k": per_frame[0]}
        return {"a": 1,
                "k": [{"t": float(f), "s": [b]} for f, b in zip(frames, per_frame)]}
```

`_build_layers` lấy mẫu mọi frame trong dải và **khẳng định ổn định cấu trúc**
qua `_assert_stable`: nếu số đỉnh hoặc cờ `c` của một shape đổi giữa các frame,
nó nâng một lỗi rõ ràng nêu tên layer, tên shape và hai frame. Phép đo nói
điều này không bao giờ xảy ra (0 không ổn định trong 2.659 shape) - đã xác nhận
vẫn đúng sau các thay đổi của chính nhiệm vụ này, vì `_assert_stable` không bao
giờ nổ trên bất kỳ tài liệu nào trong 18 tài liệu xuất thành công.

Danh sách frame là mọi số nguyên trong `[start_frame, end_frame]` (xem mặc định
của chính `main()`, được thêm ở nhiệm vụ này: trước đây `--frame` là bắt buộc).

- [x] **Bước 4: Chạy lại check hình học**

Đã chạy với `Bandit.mohoproj` (frame 25/40/60/87/127) và, đi xa hơn những gì
kế hoạch yêu cầu, `WhatIsBone.animeproj` (frame 1/60/120/180/240) và
`OffsetBoneTool.animeproj` (frame 1/12/24) - `OK` trên mọi frame của mọi tài
liệu được kiểm.

Cũng chạy một smoke export toàn-kho (`--out` không `--frame`, tức toàn dải)
trên cả 19 tài liệu mẫu: **18 thành công**; `SketchBone.animeproj` nâng
`ValueError` về độ thấy được của SwitchLayer mô tả ở trên, điều được dự kiến và
hoãn đến Nhiệm vụ 7.

- [x] **Bước 5: Kiểm kích thước so với ước lượng của thiết kế**

`Bandit.mohoproj`: 932.584 byte thô, 35.218 byte gzipped - nằm gọn trong ước
lượng ~1.8 MB của thiết kế.
`WhatIsBone.animeproj` (tài liệu lớn nhất, hoạt ảnh nhiều nhất, 227 frame):
18.641.999 byte thô, 1.774.737 byte gzipped (~10.5x) - lớn về giá trị tuyệt đối
nhưng tối ưu path TĨNH được xác nhận đang nổ (đã xác minh trực tiếp:
`AddBone.animeproj`, thứ có dòng thời gian chính không hoạt ảnh gì cả, sinh ra
đầu ra byte-IDENTICAL dù được xuất ở một frame đơn hay toàn dải 175-frame của
nó - 291.936 byte cả hai cách, 0 phần tử `"sh"` được keyframe, cả 336 đều tĩnh).

- [x] **Bước 6: Commit**

```bash
git add moho2lottie.py tools/check_lottie_geometry.py
git commit -m "Bake Moho deformation into Lottie path keyframes"
```

---

## Nhiệm vụ 5: Gradient

**Trạng thái:** DONE — một khoảng trống thiết kế thật trong phác thảo gốc: nó
coi vị trí gradient là tĩnh (`"a": 0`), tính một lần. Đã sửa bằng cách làm các
điểm "s"/"e" THEO-FRAME thay thế - xem ghi chú bên dưới.

**⚠ Vị trí gradient phải được keyframe, không phải tĩnh — phác thảo gốc bỏ sót
cái này.** Các điểm `s`/`e` của một gradient được suy ra từ bounding box RIÊNG
của shape (khớp các phần trăm SVG `objectBoundingBox` của
`Exporter._build_gradient`). Cái hộp đó di chuyển theo shape - hầu hết shape
tô-gradient trong kho này nằm trên các layer bị biến dạng bởi bone - nên đóng
băng nó tại frame 0 sẽ tách gradient khỏi một shape chuyển động/biến dạng một
cách thấy được. Đã xác nhận dữ liệu NGUỒN của gradient (màu/vị trí stop,
`gradient_type`, `effect_scale`, `effect_rotation`) thật sự bất biến-frame ở mọi
nơi trong kho này (0 instance hoạt ảnh của bất kỳ cái nào trong chúng, được
kiểm trực tiếp trên cả 19 tài liệu) - chỉ bản thân hộp di chuyển. Đã sửa bằng
cách tách xử lý gradient thành `_eval_gradient` (phần bất biến-frame, được đánh
giá một lần trong `_new_accumulator`, đúng như màu fill/line) và `_gradient_fill`
(chạy trong `_finalize_shapes`, thứ tính lại bounding box từ dữ liệu
`fill_per_frame` ĐÃ-GOM-CỦA-mỗi-frame - không cần lời gọi `exp.eval()`/`to_px()`
thừa, nên cái này không mở lại mối nguy lỗi thời của Nhiệm vụ 4) sinh ra một
`_point_property` mới (đối tác điểm-2D của `_scalar_property`) cho `s`/`e`.

Cũng được tìm thấy và tái hiện một cách cố ý, không sửa:
`Exporter._build_gradient` rơi về `fill_color` phẳng trơn của shape bất cứ khi
nào nó có ít hơn 2 stop (xem `_render_shape`: `paint = fill_hex` là mặc định,
chỉ bị ghi đè khi một def gradient thật sự thành công). `_eval_gradient` phản
chiếu fallback đó chính xác và đếm nó (`gradient_too_few_stops`) thay vì thầm
lặng vẽ không gì hoặc crash - được đo là không bao giờ thật sự nổ trên toàn kho
mẫu, nhưng kho không phải một bằng chứng rằng nó không bao giờ có thể.

**Các file:**
- Sửa: `moho2lottie.py` — `_new_accumulator` (lời gọi `_eval_gradient` mới), `_finalize_shapes` (`_gradient_fill`, `_bbox_of_beziers`, `_gradient_endpoints`, `_point_property` mới)
- Sửa: `tools/check_lottie_geometry.py` — đã có `--require-gradients` từ việc viết của chính Nhiệm vụ 4; không đổi ở nhiệm vụ này

**Giao diện:**
- Sinh ra: một phần tử `"ty": "gf"` thay cho `"ty": "fl"` khi `shape.style.fill_style["type"] == "SS_Gradient2"` **và** nó giải quyết thành 2 stop trở lên; khóa `"gradient"` của accumulator (`None`, hoặc một dict với `stops`/`stop_count`/`lottie_type`/`scale`/`rotation`) là thứ `_finalize_shapes` rẽ nhánh theo.

- [x] **Bước 1: Tìm một tài liệu luyện tập nó**

Chạy:
```bash
python3 -c "
import json
d=json.load(open('moho/Bandit.mohoproj'))
n=0
def w(x):
    global n
    if isinstance(x,dict):
        if x.get('type')=='SS_Gradient2': n+=1
        for v in x.values(): w(v)
    elif isinstance(x,list):
        for v in x: w(v)
w(d); print('SS_Gradient2 occurrences:', n)"
```
Dự kiến: một số khác không. Nếu nó là không, chọn một tài liệu khác từ `moho/`
trước khi viết check.

- [ ] **Bước 2: Viết assertion dự kiến fail**

Thêm vào `tools/check_lottie_geometry.py` một cờ `--require-gradients` fail khi
file phát ra không chứa phần tử `"ty": "gf"` nào trong khi tài liệu nguồn chứa
một style `SS_Gradient2`.

Chạy với `Bandit.mohoproj`: không áp dụng được (0 lần xuất hiện `SS_Gradient2`,
theo Bước 1). Thay vào đó chạy với `WhatIsBone.animeproj` (68 lần xuất hiện,
nhiều nhất trong mọi tài liệu mẫu): đã xác nhận `--require-gradients` FAILED
trước Bước 3, vì chưa có phần tử `"gf"` nào tồn tại.

- [x] **Bước 3: Phát `gf`**

Được triển khai như `_eval_gradient` (phần bất biến-frame - stops, type, scale,
rotation) cộng `_gradient_fill`/`_bbox_of_beziers`/`_gradient_endpoints` (phần
vị trí theo-frame) - xem ghi chú "vị trí gradient phải được keyframe" ở trên về
việc vì sao đây là hai hàm, không phải một hàm như kế hoạch gốc.

`gradient_type` của Moho là 0 linear / 1 radial; `t` của Lottie là 1 linear / 2
radial, nên ánh xạ không phải đồng nhất — được viết ra thay vì cộng 1.

`_gradient_endpoints` suy ra hai điểm từ bounding box pixel của shape (được tính
lại mới mỗi frame từ `fill_per_frame`, không được cache từ một frame đơn) và
`effect_scale`/`effect_rotation` đã đánh giá một lần, khớp công thức của chính
`Exporter._build_gradient`.

- [x] **Bước 4: Chạy lại cả hai check**

Đã chạy với `WhatIsBone.animeproj` (frame 1/60/120/180/240,
`--require-gradients`): `OK`. Cũng chạy tương tự với `Bandit.mohoproj`, để xác
nhận `--require-gradients` đúng là một no-op khi nguồn không có gradient gì cả:
`OK`.

Đã đi xa hơn hai check của chính kế hoạch:
- Đã soi cấu trúc phát ra trực tiếp: 68 phần tử `"gf"` trong đầu ra của
  `WhatIsBone.animeproj`, cả `t: 1` (linear) lẫn `t: 2` (radial) đều hiện diện,
  mỗi cái 2 stop (độ dài `g.k.k` 8 = 2 × 4 số), `s`/`e` đều được keyframe
  (`"a": 1`) với giá trị bám theo một bounding box chuyển động từ frame này
  sang frame khác một cách thấy được - xác nhận sửa vị-trí-keyframe thật sự gắn
  vào, không chỉ parse.
- Đã chạy một smoke export toàn-kho (18 trong 19 tài liệu, cùng ngoại lệ
  `SketchBone.animeproj` SwitchLayer được dự kiến như Nhiệm vụ 4): không crash,
  và `gradient_too_few_stops` nổ trên không shape nào trên toàn kho, nhất quán
  với phép đo đếm-stop toàn-kho từ check rộng hơn của Bước 1.
- Đã chạy lại `make gen` (byte-identical) và `check_bezier_roundtrip.py` (vẫn
  qua trên cả 19 tài liệu) - nhiệm vụ này chỉ đụng vào việc chọn sơn phần tô,
  không bao giờ hình học path, nên cả hai đều không nên xê dịch, và cả hai đều
  không.

- [x] **Bước 5: Commit**

```bash
git add moho2lottie.py tools/check_lottie_geometry.py
git commit -m "Write Moho gradients as Lottie gradient fills"
```

---

## Nhiệm vụ 6: Masking

**Trạng thái:** DONE — một khoảng trống thiết kế thật trong phác thảo bên dưới
(hình học mask bị coi là tĩnh, cùng loại sai lầm như vị trí gradient của Nhiệm
vụ 5), cộng một lần cắt phạm vi cố ý, được đếm (khoét bỏ loại-trừ-stroke). Đọc
cả hai ghi chú trước khi đụng vào code này.

**⚠ Hình học mask cũng phải được keyframe - đã đo, không phải giả định.** Hình
học của chính một mask source chuyển động/biến dạng đúng như hình học của bất
kỳ shape nào khác. Đã kiểm trực tiếp trước khi viết bất kỳ code nào: **4 trong
4 container bị mask trong `Bandit.mohoproj`, 17 trong 17 trong
`SketchBone.animeproj`** có hình học mask source KHÁC NHAU qua ba frame được lấy
mẫu - không phải một trường hợp góc, mà là chuẩn. Nên mask được gom **theo từng
frame**, đúng như hình học shape (Nhiệm vụ 4) và vị trí gradient (Nhiệm vụ 5):
`_build_layers` giờ cũng xử lý các event `"enter"`/`"exit"` mà trước đây nó bỏ
qua, duy trì một `mask_stack` **được dựng lại mới mỗi frame** (không bao giờ
mang qua các frame - cấu trúc ngoặc của một phạm vi mask chỉ hợp lệ trong bước
duyệt của riêng một frame), và gọi một `Exporter._mask_sources_bezier` mới
**một cách đồng bộ**, đúng lúc mỗi event `"enter"` được thấy, vì cùng lý do lỗi
thời đã lập trong Nhiệm vụ 4.

**Cố ý không tái hiện: khoét bỏ loại-trừ-stroke.** `Exporter._mask_element`
(phía SVG) sơn dải đường viền của riêng một mask source bằng MÀU ĐEN lên trên
phần tô union, để nét viền của riêng source đó vẫn thấy được trên bất cứ thứ gì
mask cắt. Mô hình mask của Lottie chỉ có shape được tô - không có primitive "tô
nét path này như một mask" - nên tái hiện chính xác điều này nghĩa là dựng một
polygon dải stroke-bề rộng-đều cho mỗi source, một dự án riêng của nó cho một
hiệu ứng hẹp: được đo ở **16 trong 180 shape mask source (9%)** với một bề rộng
loại trừ khác không, trên cả 19 tài liệu mẫu. Đã bỏ, nhưng **được đếm**
(`mask_stroke_exclusion`), không thầm lặng - xem Ràng buộc toàn cục về cái này.

**Các file:**
- Sửa: `moho2svg.py` — `Exporter._mask_source_shapes_bezier`/`_mask_sources_bezier` mới (anh em bezier của các phương thức chuỗi-SVG hiện có, thuần cộng thêm - các bản gốc chỉ-SVG không bị đụng)
- Sửa: `moho2lottie.py` — `_build_layers` (giờ cũng tiêu thụ `"enter"`/`"exit"`), `_finalize_mask` mới, `_shape_layer` có thêm một tham số `mask_properties`

**Giao diện:**
- Sinh ra: `"hasMask": True` và một danh sách `"masksProperties"` trên mọi mesh layer không `exempt` và nằm trong một phạm vi `"enter"` có các mask source riêng không rỗng - được xác định một lần (frame 0) cho mỗi layer và được khẳng định ổn định sau đó (nâng lỗi nếu nó bao giờ đổi, vì cấu hình masking là một trường Layer tĩnh, không phải một Channel).
- `Exporter._mask_sources_bezier(container, chain_through_container, frame) -> list[tuple[list[dict], float]]` — cùng cặp `(geometry, exclude_width)` như `_mask_sources` hiện có, đầu ra `build_path_bezier` thay cho một chuỗi SVG `d`.

**Ghi chú (không đổi so với phác thảo gốc):** chỉ mask của container TRỰC
TIẾP bao quanh mới bao giờ áp dụng cho một con, không bao giờ của một ông bà -
phạm vi hóa của chính `emit` (`member_clip` được tính mới mỗi phạm vi, không bao
giờ được tích lũy) xác nhận điều này, nên `_build_layers` chỉ đọc
`mask_stack[-1]`, không bao giờ tìm sâu hơn xuống stack.

- [x] **Bước 1: Tìm các layer phải thay đổi**

Chạy:
```bash
python3 -c "
import json,os
from collections import Counter
c=Counter()
for f in sorted(os.listdir('moho')):
    if not f.endswith(('.mohoproj','.animeproj')): continue
    raw=json.load(open('moho/'+f))
    def w(n):
        if isinstance(n,dict):
            if 'masking' in n and 'uuid' in n: c[n['masking']]+=1
            for v in n.values(): w(v)
        elif isinstance(n,list):
            for v in n: w(v)
    w(raw)
print(dict(c))"
```
Dự kiến `{0: 714, 2: 93, 1: 62, 6: 6, 5: 1}` — đã xác nhận, 162 layer mang
một giá trị khác không. Đã đi xa hơn trước khi viết code: cũng đo độ ổn định
mask source qua các frame (4/4 container bị mask của Bandit, 17/17 của
SketchBone có hình học KHÁC NHAU qua các frame được lấy mẫu - xem ghi chú ở
trên), và tần suất thật của khoét bỏ loại-trừ-stroke (16 trong 180 shape mask
source, 9%) - cả hai phát hiện đều đổi thiết kế so với những gì kế hoạch này
phác thảo ban đầu.

- [x] **Bước 2: Viết assertion dự kiến fail**

`--require-masks` đã tồn tại trong `tools/check_lottie_geometry.py` (được viết
trước thời điểm trong Nhiệm vụ 4). Đã chạy với đầu ra gradient của Nhiệm vụ 5
(chưa có masking): FAILED như dự kiến trên `Bandit.mohoproj`.

- [x] **Bước 3: Phát `masksProperties`**

Được triển khai như `Exporter._mask_sources_bezier`/`_mask_source_shapes_bezier`
(anh em mới, cộng thêm trong `moho2svg.py`) cộng `LottieExporter._finalize_mask`
(mới) và một `_build_layers` mở rộng giờ tiêu thụ các event `"enter"`/`"exit"`
với một `mask_stack` theo-frame - xem hai ghi chú ở trên về việc vì sao điều
này khác phác thảo một-hàm, vị-trí-tĩnh ban đầu của kế hoạch.

Một layer với `masking in (1, 2)` là được miễn trừ và không nhận mask nào, đúng
như writer SVG đối xử với nó - được triển khai qua `not item.exempt` gác việc
`mask_stack[-1]` có được ghi cho mesh item đó hay không, không đổi so với kế
hoạch gốc.

- [x] **Bước 4: Chạy lại mọi check**

Đã chạy với `Bandit.mohoproj` (frame 25/40/60/87/127, `--require-masks`):
`OK`. Cũng chạy `WhatIsBone.animeproj` (frame 1/60/120/180/240,
`--require-masks --require-gradients` cùng nhau): `OK`.

Đã đi xa hơn hai check của chính kế hoạch:
- Đã soi cấu trúc trực tiếp: `Bandit.mohoproj` phát 10 layer bị mask; một mask
  mẫu (`Eye_Upper`, 7 mục masksProperties) có một `pt` được keyframe đầy đủ
  (103 keyframe, khớp dải 103-frame của tài liệu) - xác nhận sửa mask-keyframe
  thật sự gắn vào.
- Đã chạy một smoke export toàn-kho: 18 trong 19 tài liệu thành công (cùng
  ngoại lệ `SketchBone.animeproj` SwitchLayer được dự kiến từ Nhiệm vụ 4-5,
  không phải một failure mới).
- `mask_stroke_exclusion` nổ đúng và cụ thể - 32 lần xuất hiện trên
  `Bandit.mohoproj` (một đếm theo-layer-NHẬN: vài anh em bị mask có thể dùng
  chung một phạm vi mask, nên đây là một con số khác, lớn hơn phép đo
  16-shape-tổng-cộng của kho từ Bước 1, và cả hai đều đúng - chúng đếm những
  thứ khác nhau).
- `make gen` (byte-identical) và `check_bezier_roundtrip.py` (cả 19 tài liệu)
  chạy lại sạch: các phương thức `moho2svg.py` mới là anh em cộng thêm của code
  mask chỉ-SVG hiện có, không bao giờ đụng vào nó.

- [x] **Bước 5: Commit**

```bash
git add moho2lottie.py moho2svg.py tools/check_lottie_geometry.py
git commit -m "Carry Moho masking into Lottie as per-layer masks"
```

---

## Nhiệm vụ 7: Switch layer

**Trạng thái:** DONE — với cách sửa, **cả 19 tài liệu mẫu giờ xuất thành công
toàn dải frame của chúng** (giới hạn `SketchBone.animeproj` được nêu trong
Nhiệm vụ 4-6 đã được giải quyết). Hai bug thật hiện ra trong lúc triển khai cái
này, cả hai đều đáng đọc trước khi đụng lại code này.

**⚠ Bug 1: thứ tự vẽ hỏng cho bất kỳ layer nào không hiện diện tại frame 0.**
Danh sách `order` có sẵn được dựng bằng cách nối thêm một layer vào lần đầu
tiên nó từng được thấy TRONG LÚC DUYỆT CÁC FRAME THEO TRÌNH TỰ - đúng cho một
tài liệu nơi mọi layer luôn hiện diện (bước duyệt của frame 0 đã khớp thứ tự
cấu trúc thật của tài liệu), nhưng sai ngay khoảnh khắc lần xuất hiện đầu của
một layer nằm giữa dải: một shape miệng lip-sync chỉ trở nên hoạt động tại
frame 77 bị nối vào `order` muộn hơn nhiều so với vị trí anh em thật của nó,
xáo trộn thứ tự vẽ của nó so với mọi layer luôn-hiện-diện một khi
`collected.reverse()` chạy. Đã xác nhận bởi `tools/check_lottie_geometry.py`:
các lỗi "layer order mismatch", nhưng chỉ bên trong cửa sổ lip-sync (frame
77-85), không nơi nào khác - đúng triệu chứng của một layer có vị trí phụ thuộc
KHI nó được phát hiện thay vì NƠI nó thuộc về về mặt cấu trúc. Đã sửa bằng cách
gieo `order` từ `Document.vector_layers()` thay thế - một bước duyệt tĩnh của
mọi mesh layer theo thứ tự file bất kể con SwitchLayer nào tình cờ đang hoạt
động tại một frame bất kỳ, thứ là nguồn chân lý thật cho thứ tự vẽ tương đối.

**⚠ Bug 2: một lần xuất preview một-frame (`--frame N`) sụp đổ ngắn ngủi độ
thấy được của mọi layer về một frame.** Suy ra `ip`/`op` thuần từ biên cửa sổ
riêng của một layer là đúng khi `frames` là toàn dải tài liệu, nhưng khi
`len(frames) == 1` (chế độ preview-tĩnh `--frame N` của Nhiệm vụ 3), "cửa sổ"
của mọi layer tầm thường trở thành đúng cái frame được lấy mẫu đó - nên một
lần xuất ảnh tĩnh ngừng giữ cho khoảng thời gian tài liệu đã khai báo, thầm
lặng đổi hành vi đã lập của chính Nhiệm vụ 3. Đã xác nhận bằng cách chạy lại
check bất biến path-tĩnh của Nhiệm vụ 4 (`AddBone.animeproj` tại `--frame 1`
so với toàn dải của nó phải byte-identical): kích thước lệch nhau 90 byte sau
thay đổi cửa sổ hóa, nơi chúng khớp chính xác trước nó. Đã sửa bằng cách đối
xử đặc biệt `len(frames) == 1` để dùng toàn dải riêng của tài liệu cho `ip`/`op`,
khôi phục bất biến gốc (đã xác minh lại: byte-identical lần nữa).

**Các file:**
- Sửa: `moho2lottie.py` — `_build_layers` (giờ gieo `order` từ `Document.vector_layers()`, theo dõi `active_frames`, và xử lý trường hợp preview-tĩnh `len(frames) == 1`), `_windows`, `_slice_accumulators` mới; `_shape_layer` có thêm các tham số `ip`/`op`
- Sửa: `tools/check_lottie_geometry.py` — `emitted_layers` giờ bỏ qua một layer có `ip`/`op` riêng loại trừ frame đang kiểm, thay vì crash trên một keyframe thiếu

**Giao diện:**
- Sinh ra: một layer phát ra cho mỗi cửa sổ liền kề (một chuỗi tối đa các giá trị frame liên tiếp) trong đó một Moho layer nhất định là event "mesh" hoạt động, với `ip`/`op` đặt theo cửa sổ đó — ngoại trừ khi toàn bộ lần xuất là một ảnh tĩnh một-frame (`len(frames) == 1`), nơi `ip`/`op` là toàn dải riêng của tài liệu thay thế (xem Bug 2 ở trên).

- [x] **Bước 1: Xác nhận một tài liệu luyện tập nó**

Chạy:
```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from moho2svg import load_document, LayerKind
import os
for f in sorted(os.listdir('moho')):
    if not f.endswith(('.mohoproj','.animeproj')): continue
    d = load_document('moho/'+f)
    n = sum(1 for _, l in d.walk() if l.kind is LayerKind.SWITCH)
    if n: print(f, n, 'switch layers')"
```
**Đã xác nhận.** `SketchBone.animeproj` (đã biết, từ failure `agiz`/lip-sync
của chính Nhiệm vụ 4) là một tài liệu switch-layer thật, với một luân phiên
8-ngả cho shape miệng.

- [x] **Bước 2: Viết assertion dự kiến fail**

Các cờ kiểu `--require-masks`/`--require-gradients` không phải hình dạng đúng
cho cái này - thứ thật sự cần mở rộng là bản thân `emitted_layers` (xem ghi chú
sửa bug ở trên): trước nhiệm vụ này, nó crash ngay (`KeyError: no keyframe at
frame N`) trên bất kỳ frame nào ngoài cửa sổ của một layer, vì mọi layer vẫn bị
giả định giữ một keyframe tại mọi frame được kiểm. Đã sửa để bỏ qua một layer
có `ip`/`op` riêng loại trừ frame đang kiểm - đã xác nhận riêng điều này không
che bug thật, vì nó vẫn PHƠI cả hai bug mô tả ở trên một khi crash được dọn
đường.

Đã chạy trước khi Bước 3 tồn tại (tức trước khi cửa sổ hóa được triển khai
hoàn toàn): `moho2lottie.py moho/SketchBone.animeproj` fail ngay với `ValueError`
đã biết từ Nhiệm vụ 4 ("'agiz' shape '': only 111/120 frames were captured") -
xác nhận điểm khởi đầu là "không thể xuất gì cả," không phải "xuất với hình học
sai."

- [x] **Bước 3: Phát các cửa sổ**

Được triển khai như `_windows` (một static method - phác thảo của chính kế
hoạch đặt tên nó là `_switch_windows`, giữ tên đơn giản hơn vì nó hoạt động
trên danh sách active-frame của bất kỳ layer nào, không riêng "switch windows")
cộng `_slice_accumulators` và một `_build_layers` mở rộng - xem hai ghi chú sửa
bug ở trên cho hai đính chính ngoài phác thảo một-hàm ban đầu của kế hoạch.

`ip`/`op` của mọi layer phát ra đến từ cửa sổ của nó thay vì dải tài liệu -
ngoại trừ trường hợp đặc biệt preview-một-frame (Bug 2 ở trên).

- [x] **Bước 4: Chạy lại các check**

Đã chạy `check_lottie_geometry.py` với `SketchBone.animeproj` tại bảy frame
trải qua cả hai ranh giới cửa sổ (1, 76, 77, 80, 85, 86, 120 - frame 1 và 120
là hai cửa sổ lớn luôn-miệng-đóng, 77/80/85 lấy mẫu bên trong ba cửa sổ
một-viseme khác nhau, 76/86 nằm chính xác trên một chuyển tiếp): `OK` trên cả
bảy, kể cả `--require-gradients`.

Đã đi xa hơn check hai-frame của chính kế hoạch:
- Đã soi cấu trúc trực tiếp: `SketchBone.animeproj` phát 8 layer riêng tên
  `agiz`, các cửa sổ của chúng lát kín `[1, 121)` một cách chính xác không khe
  hở hay chồng lấn (1-77, 77-79, 79-81, 81-83, 83-85, 85-86, 86-121, đã xác
  nhận bằng soi trực tiếp).
- Đã chạy một smoke export toàn-kho: **19 trong 19 tài liệu giờ thành công** -
  cột mốc mà nhiệm vụ này tồn tại vì nó.
- Đã chạy lại bất biến path-tĩnh của Nhiệm vụ 4 trên `AddBone.animeproj` (đầu
  ra `--frame 1` phải byte-identical với đầu ra toàn-dải) - đây là thứ bắt Bug
  2 ở trên, và qua lần nữa sau cách sửa.
- Đã xác minh lại `Bandit.mohoproj`/`WhatIsBone.animeproj`/`OffsetBoneTool.animeproj`
  (`--require-masks`/`--require-gradients` nơi áp dụng được) vẫn qua, xác nhận
  sửa xây-dựng-`order` (Bug 1) không làm xáo trộn bất kỳ tài liệu nào không có
  switch layer gì cả.
- `make gen` (byte-identical) và `check_bezier_roundtrip.py` (cả 19 tài liệu)
  chạy lại sạch.

- [x] **Bước 5: Commit**

```bash
git add moho2lottie.py tools/check_lottie_geometry.py
git commit -m "Emit switch layer children as Lottie visibility windows"
```

---

## Nhiệm vụ 8: Cảnh báo, make target và xác thực schema tùy chọn

**Trạng thái:** DONE — và nhiệm vụ này là lý do vị trí gradient `s`/`e` của
exporter SAI theo schema Lottie từ Nhiệm vụ 5 trở đi, không bị phát hiện bởi
mọi check viết trước cái này. Đọc ghi chú bên dưới trước bất cứ thứ gì khác
trong mục này.

**⚠ Bug do chính --validate tìm thấy: `_point_property` bọc hai lần giá trị "s"
của nó.** Mọi check viết trong Nhiệm vụ 4-7 (`tools/check_lottie_geometry.py`)
so đầu ra của chính exporter với chính nó (một lời gọi thứ hai đến cùng
pipeline) hoặc với `build_path_bezier()` trực tiếp - không cái nào bao giờ parse
một giá trị theo SCHEMA Lottie, nên một giá trị thỏa "writer đồng ý với chính
nó" vẫn có thể vi phạm định dạng. `_point_property` (được thêm trong Nhiệm vụ 5
cho gradient `s`/`e`, được dùng lại không đổi từ đó) viết `"s"` của một
keyframe như `[[x, y]]` - chép QUY ƯỚC SAI từ các keyframe bezier của chính
`_path_property`, nơi `"s": [b]` (một mảng chứa đúng một giá trị bezier) là đúng
vì schema của `bezier-keyframe` tường minh muốn sự bọc đó. Schema của chính một
keyframe vị-trí/vector (`vector-keyframe`, được chia sẻ bởi position-property
LẪN scalar-property của Lottie) muốn `"s"` là mảng FLAT trực tiếp - `[x, y]`,
không phải `[[x, y]]`. Chạy `--validate` (cài qua một venv dùng một lần, không
bao giờ được thêm như một dependency dự án) lần đầu tiên phơi cái này ngay lập
tức: 2 trong 19 tài liệu mẫu (`SketchBone.animeproj`, `WhatIsBone.animeproj` -
hai cái dùng gradient nhiều nhất) fail xác thực schema với một bất khớp `oneOf`
trên đúng trường này. Đã sửa bằng cách bỏ sự bọc thừa; **cả 19 tài liệu giờ
validate sạch** (đã xác nhận bằng cách thật sự cài `jsonschema` trong một
virtualenv cô lập và chạy nó - không chỉ bằng cách đọc code). `_scalar_property`
đã đúng một cách tình cờ: bọc một SỐ duy nhất trong một danh sách (`[v]`) sinh
ra chính xác mảng flat mà `values/vector` muốn, nên cùng sai lầm "bọc nó như
một bezier" tình cờ vô hình ở đó.

Đây là bằng chứng mạnh nhất trong toàn dự án về việc vì sao sự tồn tại của
`--validate` đáng giá dependency tùy chọn: các check so-hình-học một mình, dù
kỹ lưỡng đến đâu, không thể bắt một sai lầm cấp-định-dạng nếu cả hai phía của
phép so sánh dùng chung cùng một bug.

**Các file:**
- Sửa: `moho2lottie.py` (cảnh báo đã tồn tại từ Nhiệm vụ 3 trở đi - chỉ được xác minh ở đây; `validate_lottie`, `--validate` mới, và sửa `_point_property` ở trên), `Makefile`, `.gitignore`

- [x] **Bước 1: In tóm tắt cảnh báo**

Đã được triển khai, tăng dần, bắt đầu từ Nhiệm vụ 3 (`combo_mode`, `brush`) và
được mở rộng trong Nhiệm vụ 5-6 (`gradient_too_few_stops`,
`mask_stroke_exclusion`) - `WARNING_EXPLANATIONS` và vòng lặp in trong `main()`
không cần thay đổi gì ở nhiệm vụ này. Đã xác minh cả bốn khóa vẫn in đúng, một
dòng cho mỗi bộ đếm khác không, ra stderr, nêu tên thứ đã bị bỏ.

- [x] **Bước 2: Thêm xác thực schema tùy chọn**

```python
try:
    import jsonschema
except ImportError:                     # optional, exactly like Pillow
    jsonschema = None
```

`--validate` xác thực theo `lottie/lottie.schema.json` khi `jsonschema` import
được, và nếu không thì in một dòng nói rằng việc xác thực đã bị bỏ qua và cách
bật nó. Docstring của chính nó ghi chú rằng việc qua là bằng chứng yếu: schema
đánh dấu rất ít là bắt buộc (`lottie-and-thorvg.md` § 2.5) - đúng, nhưng nó vẫn
bắt một bug thật ngay lập tức (xem ở trên), nên "bằng chứng yếu" nghĩa là
"không phải bằng chứng đúng đắn", không phải "không đáng chạy."

- [x] **Bước 3: Thêm các make target**

Được triển khai như kế hoạch, với một bổ sung: `gen-lottie` nhận một make
variable `VALIDATE` (`make gen-lottie VALIDATE=--validate`) để xác thực schema
cũng có thể được chọn vào từ `make`, không nhân đôi các lệnh xuất trong một
target riêng. Các check hình học của riêng `check-lottie` được mở rộng hơi quá
phác thảo một-tài-liệu của kế hoạch để cũng phủ `SketchBone.animeproj`
(`--require-gradients`, luyện cửa sổ hóa của Nhiệm vụ 7) và
`WhatIsBone.animeproj` (`--require-masks --require-gradients`), vì riêng Bandit
không luyện các cửa sổ switch-layer.

- [x] **Bước 4: Bỏ qua thư mục đầu ra**

Đã thêm `lottie-out/` vào `.gitignore`, bên cạnh các mục `svg-fast/`/`svg-med/`/
`svg-raster/` hiện có.

- [x] **Bước 5: Chạy mọi thứ**

Đã chạy `make check-lottie`: cả ba check `OK`. Đã chạy `make gen`: `git diff
--stat -- svg/` rỗng.

Đã đi xa hơn lần chạy đơn của chính kế hoạch: chạy `make gen-lottie
VALIDATE=--validate` (qua một virtualenv cô lập với `jsonschema` được cài,
không bao giờ được thêm như một dependency dự án) trên cả 19 tài liệu mẫu từng
cái một, không chỉ ba cái được theo dõi bởi `gen-lottie` - đây là thứ bắt bug
`_point_property` ở trên. Đã chạy lại sau sửa: **19 trong 19 qua xác thực
schema** (riêng `WhatIsBone.animeproj` mất ~48s để validate vì kích thước của
nó - được ghi chú ở đây vì một lần chạy lại ngây thơ với một timeout ngắn trông
như treo, không phải một check chậm-nhưng-thành-công).

- [x] **Bước 6: Cập nhật tài liệu**

Đã cập nhật các mục "What this is", bố cục repo, và Commands của `CLAUDE.md`
với `moho2lottie.py`, `tools/`, và `lottie-out/`. Đã viết lại phần mở đầu của
`moho-to-lottie-design.md` để trỏ vào tài liệu kế hoạch này thay vì tuyên bố
không gì được triển khai, và cập nhật mục 9 Câu hỏi mở của chính nó với kết quả
mỗi mục giải quyết thành (ba đã chốt: thứ tự-shape được né theo thiết kế,
masking được triển khai và kiểm hình học, kích thước gzip được xác nhận ổn ở
mức nén ~10x; hai vẫn thật sự mở, cả hai đều cần một Lottie player thật mà dự
án này chưa bao giờ dựng hay chạy; một - bản gương tiếng Việt - vẫn cố ý hoãn,
không được thử).

- [x] **Bước 7: Commit**

```bash
git add moho2lottie.py Makefile .gitignore CLAUDE.md docs/moho-to-lottie-design.md docs/moho-to-lottie-plan.md
git commit -m "Add make targets and warning output for the Lottie exporter"
```

---

## Sau kế hoạch

Cả 8 nhiệm vụ đều xong (xem bảng Tiến độ). Hai câu hỏi mở từ thiết kế còn lại,
và không cái nào có thể được chốt bởi bất cứ thứ gì trong kế hoạch này, vì cả
hai đều cần một Lottie player thật - thứ không phần nào của dự án này từng
dựng, cài, hay chạy:

1. **`op` của Lottie có loại trừ không?** `LottieExporter.export` giả định
   `end_frame + 1`.
2. **Khiếm khuyết thứ tự kế thừa `masking == 2` của `Bandit.mohoproj` (được
   ghi trong docstring module của chính `moho2svg.py`) thấy rõ hơn hay kém hơn
   trong một Lottie player so với một player SVG?** Không biết theo cả hai
   hướng.

(Mục 2 gốc của chính thiết kế, "một paint operator trong một group có áp dụng
cho các shape mà writer định ý không", hóa ra đã được giải quyết THEO THIẾT KẾ,
không phải bởi một player: Nhiệm vụ 3 cho mỗi shape lên tới hai group Lottie
riêng biệt - một cho phần tô, một cho nét viền - cụ thể để không group nào bao
giờ có nhiều hơn một shape-lượng hình học trước paint operator duy nhất của nó.
Không còn gì cho một player phải phân biệt.)

Cả hai câu hỏi còn lại đều được chốt bằng cách tải `lottie-out/Bandit.json`
trong lottie-web bên cạnh `svg/Bandit.svg`. Cho đến khi điều đó xảy ra,
exporter được xác minh là *tự nhất quán với writer SVG và schema-valid*, một
khẳng định mạnh, nhưng không giống *đúng trong một player*. Hãy nói như vậy
trong bất kỳ báo cáo nào về công việc này.
