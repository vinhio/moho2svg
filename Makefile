# ---------------------------------------------------------------------------
# `make` with no target prints this help - the help target is the first real
# target in the file, so GNU make makes it the default goal. Each entry shows
# an example command; the pattern rules let you build any project by name,
# e.g. `make out/svg/ori/Bandit.svg` - see the sections below for details.
.PHONY: help
help:
	@echo 'Usage: make [TARGET]'
	@echo ''
	@echo 'Aggregate targets:'
	@echo '  make help                              show this help'
	@echo '  make svg-all                           every moho/ project in all four svg forms'
	@echo '  make lottie-all                        every moho/ project -> out/lottie/'
	@echo '  make lottie-all VALIDATE=--validate    also schema-validate each export'
	@echo '  make out/lottie/DarkMan.json LOTTIE_EXPORT_FLAGS=--point-bones LOTTIE_DECIMATE_TOLERANCE=2.0'
	@echo '                                        shrink one lottie export (see moho2lottie.py --decimate-tolerance /'
	@echo '                                        --rigid-transform-tolerance, and LOTTIE_RIGID_TOLERANCE)'
	@echo '  make out/lottie/BoneStrengthTool.json IMAGE_DIR=/Applications/Moho.app/Contents/Resources/Support'
	@echo '                                        (or any SVG/lottie target) resolve ImageLayer sources -'
	@echo '                                        see moho2svg.py --image-dir'
	@echo '  make check-lottie                      verify lottie output (no player needed)'
	@echo '  make check-reference                   compare geometry vs Moho 14.4 exports'
	@echo '  make format                            pretty-print every moho/ project'
	@echo ''
	@echo 'Setup:'
	@echo '  make venv                              create .venv and install optional packages'
	@echo '                                        (Pillow, psd-tools, pyclipper) - every target below then'
	@echo '                                        uses it automatically, no activation needed'
	@echo ''
	@echo 'Single-file targets (build any project by name):'
	@echo '  make out/svg/ori/Bandit.svg            one original export (full brush texture)'
	@echo '  make out/svg/med/SketchBone.svg        one medium-density preview'
	@echo '  make out/svg/fast/WhatIsBone.svg       one fast preview (no brush stamping)'
	@echo '  make out/svg/raster/Bandit.svg         one raster brush export (needs Pillow)'
	@echo '  make out/svg/ori/BoneStrengthTool.svg  IMAGE_DIR=/Applications/Moho.app/Contents/Resources/Support'
	@echo '                                        (or any SVG target) resolve ImageLayer sources -'
	@echo '                                        see moho2svg.py --image-dir'
	@echo '  make out/svg/ori/png/SketchBone.png    render one ori SVG to PNG (3x)'
	@echo '  make out/lottie/Bandit.json            one lottie export'
	@echo '  make format/moho/Bandit                pretty-print one project (moho/Bandit.json)'
# ---------------------------------------------------------------------------
# One-time environment setup. The exporters never REQUIRE a third-party
# package - every missing one falls back gracefully - but three are worth
# installing: Pillow (fast brush-texture rendering, --brush-raster),
# psd-tools (rendering an ImageLayer's referenced PSD layers via --image-dir;
# it also needs Pillow), and pyclipper (moho2lottie.py pre-clips a
# combo_mode==3 shape's own fill/outline against its group's base union at
# EXPORT time instead of via a Lottie masksProperties mode "i" entry, which
# is not reliably honoured by every real-world player - confirmed silently
# ignored by both lottie-web's canvas renderer and LottieFiles' own preview
# player; see moho2lottie.py's _clip_polygon_loops). The virtualenv is
# gitignored; every `make` target below already runs under it automatically
# once it exists (see the PYTHON variable, a few lines down) - no need to
# `source .venv/bin/activate` yourself before running `make` (only before
# running a script directly with a bare `python3 moho2svg.py ...`, since
# that bypasses make and its PYTHON variable entirely). (jsonschema stays
# out of the venv - it is needed only by `moho2lottie.py --validate`, so
# `pip install jsonschema` it on demand instead.)
.PHONY: venv
venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install Pillow psd-tools pyclipper
# ---------------------------------------------------------------------------
# Pattern rules: the output file IS the target, so you can build any project
# by name from the command line, e.g.:
#   make out/svg/ori/Bandit.svg          # one reference SVG
#   make out/svg/med/SketchBone.svg      # one medium-density preview
#   make svg-all                         # every project, all four svg forms
# The source project is picked up under moho/ by matching the target's stem
# against BOTH extensions (.animeproj first, .mohoproj second), so a
# target like `out/svg/ori/SketchBone.svg` resolves to moho/SketchBone.animeproj
# while `out/svg/ori/Bandit.svg` resolves to moho/Bandit.mohoproj. `.SECONDEXPANSION`
# is what lets the pattern prerequisite run `$(wildcard ...)` per target;
# the .py files and this Makefile are listed as prerequisites too, so the
# reference SVGs regenerate whenever the exporter or the rules change, not
# just when a .mohoproj/.animeproj file changes.
.SECONDEXPANSION:
.PHONY: svg-all lottie-all format

# PYTHON: use .venv/bin/python3 (Pillow/psd-tools/pyclipper already on its
# path) whenever `make venv` has created it, plain `python3` (no optional
# packages) otherwise - so every recipe below gets the optional-package
# path without needing `source .venv/bin/activate` first. $(wildcard ...)
# is evaluated once, when make reads this file, so `make venv` itself (which
# creates .venv/bin/python3 for the FIRST time) still has to run under
# plain `python3` - that recipe hardcodes it rather than using this
# variable, deliberately, since .venv/bin/python3 cannot exist yet at that
# point. Every other recipe uses $(PYTHON), not a literal `python3` -
# checked with `grep -n '[^N]python3' Makefile` after any edit here, since
# a literal one silently falls back to skipping every optional package
# again, the exact bug this variable exists to remove.
PYTHON := $(if $(wildcard .venv/bin/python3),.venv/bin/python3,python3)

# IMAGE_DIR (empty/unset by default, exactly like moho2svg.py's own
# --image-dir - neither guesses a Moho install path) - the local `Support/`
# directory an ImageLayer's source (e.g. a PSD in Moho's own shipped content
# library) resolves against, e.g.
# IMAGE_DIR=/Applications/Moho.app/Contents/Resources/Support on macOS. Read
# by BOTH the SVG and Lottie recipes below, so it applies to any target,
# e.g. `make out/lottie/BoneStrengthTool.json IMAGE_DIR=...`. See
# moho2svg.py's own --image-dir (same flag, same Exporter underneath) for
# what it actually does - requires the optional psd-tools/Pillow packages
# (`make venv`); an ImageLayer whose source cannot be found or opened is
# skipped with a warning either way, IMAGE_DIR set or not.
IMAGE_DIR ?=
image_dir_flag = $(if $(IMAGE_DIR),--image-dir "$(IMAGE_DIR)")

# Define the shared recipe bits once. $(1) is the output file; the input is
# found by `ls`, mirroring the wildcard prerequisite order above. `$*` is the
# pattern stem (expanded when the recipe runs, so it is the current target's
# own stem); `$$` are escaped dollars the shell will see.
define export_svg_recipe
	mkdir -p $(dir $(1))
	@src="$$(ls moho/$*.animeproj moho/$*.mohoproj 2>/dev/null | head -1)"; \
	if test -z "$$src"; then echo "no source project under moho/ for $(1)"; exit 1; fi; \
	$(PYTHON) moho2svg.py "$$src" --combined $(1) $(2) $(image_dir_flag)
endef

# Original export: full brush texture at default spacing - the closest match
# to what Moho itself exports (see docs/moho-exporting-svg.md).
out/svg/ori/%.svg: moho2svg.py Makefile $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	$(call export_svg_recipe,$@,)

# Medium-density preview: brush stamping at --brush-spacing-mul
# BRUSH_SPACING_MUL (default 2 = half the dabs of ori; override per run,
# e.g. `make out/svg/med/SketchBone.svg BRUSH_SPACING_MUL=4`).
BRUSH_SPACING_MUL ?= 2
out/svg/med/%.svg: moho2svg.py Makefile $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	$(call export_svg_recipe,$@,--brush-spacing-mul $(BRUSH_SPACING_MUL))

# Fast preview: brush stamping disabled entirely (--brush-dir ""), so a
# heavily brush-styled document (e.g. SketchBone) stays quick to open in a
# browser/SVG viewer - see docs/moho-exporting-svg.md § Brush textures.
out/svg/fast/%.svg: moho2svg.py Makefile $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	$(call export_svg_recipe,$@,--brush-dir "")

# Smallest/fastest brush export: each brush-styled shape's whole stroke is
# composited into ONE raster <image> at export time (--brush-raster) instead
# of one <use>/dab per stamp - biggest size/speed win of all the brush
# options, at the cost of that stroke no longer being vector (not rescalable/
# editable as a path afterwards), and a visible softening of fine/wispy
# textures under heavy dab overlap (see docs/moho-exporting-svg.md § 7 for the
# "golge" example). Requires Pillow.
out/svg/raster/%.svg: moho2svg.py Makefile $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	$(call export_svg_recipe,$@,--brush-raster)

# svg-all and lottie-all derive their file lists from moho/ when make parses
# the file, so a new project dropped into moho/ is picked up by the next run.
# Unique stems only: when both extensions exist for a name (SketchBone), the
# .animeproj wins the stem, matching the pattern rules above; a .mohoproj-only
# document (Bandit, SlickObjectTransition) resolves through its own stem.
PROJECT_STEMS := $(sort $(patsubst moho/%.animeproj,%,$(wildcard moho/*.animeproj)) $(patsubst moho/%.mohoproj,%,$(wildcard moho/*.mohoproj)))

# Every project in every SVG form.
svg-all: $(foreach d,out/svg/ori out/svg/med out/svg/fast out/svg/raster,$(addprefix $d/,$(addsuffix .svg,$(PROJECT_STEMS))))

# Render one reference SVG under out/svg/ori/ to a PNG under
# out/svg/ori/png/ at 3x size, e.g.:
#   make out/svg/ori/png/SketchBone.png
out/svg/ori/png/%.png: out/svg/ori/%.svg
	rsvg-convert -z 3 -o $@ $<

# Lottie export - output goes to out/lottie/, gitignored, not tracked
# reference output. Pass VALIDATE=--validate to also schema-validate each
# file against lottie/lottie.schema.json (needs the optional 'jsonschema'
# package - see moho2lottie.py's own --validate). See
# docs/moho-to-lottie-plan.md. Same pattern-rule style as the SVG exports:
# the output file is the target, e.g. `make out/lottie/Bandit.json`.
#
# LOTTIE_EXPORT_FLAGS exists so the export and the geometry check cannot drift
# apart. Both flags below CHANGE GEOMETRY, so check_lottie_geometry.py has to
# recompute with the same ones - it once ran with defaults against files
# exported with these, and reported ~100 "geometry differs" lines that were
# purely the flag mismatch. Change this variable, not the two call sites.
VALIDATE ?=
LOTTIE_EXPORT_FLAGS ?= --wind-dynamics --point-bones

# LOTTIE_DECIMATE_TOLERANCE defaults ON at 2.0px - measured (see
# docs/moho-to-lottie-design.md section 4) as a good general trade-off:
# barely-if-at-all visible, and a real win on any document with dense,
# continuous per-frame motion (DarkMan.mohoproj: 4.14 MB -> 1.94 MB); a
# document with mostly-static content pays nothing extra either way, since
# a shape that never moves was already written once (see _path_property).
# Override to 0 (empty) for byte-for-byte lossless output, e.g.
#   make out/lottie/Bandit.json LOTTIE_DECIMATE_TOLERANCE=
# or raise it for a smaller/rougher file, e.g. LOTTIE_DECIMATE_TOLERANCE=4.0.
#
# LOTTIE_RIGID_TOLERANCE stays OFF (empty) by default, unlike the above:
# measured to help almost nothing on a genuinely bone-skinned document like
# DarkMan.mohoproj (~20% of shapes qualify, none of the large ones - see
# docs/moho-to-lottie-design.md section 4), so it is opt-in per export
# rather than a blanket default, e.g.
#   make out/lottie/SomeCutoutRig.json LOTTIE_RIGID_TOLERANCE=0.5
# for a document built more like rigid cutout parts on hinges, where it can
# actually pay off.
#
# Neither is part of LOTTIE_EXPORT_FLAGS itself: unlike --wind-dynamics/
# --point-bones/--bone-dynamics, which change what "correct" geometry even
# means, a tolerance only trades size for a bounded, chosen amount of visual
# approximation - keeping these separate variables is what lets
# `make check-lottie` still verify EXACTLY that bound (via
# check_tolerance_flag below), rather than either being blind to it or
# forced back to a lossless-only check.
LOTTIE_DECIMATE_TOLERANCE ?= 2.0
LOTTIE_RIGID_TOLERANCE ?=
lottie_size_flags = $(if $(LOTTIE_DECIMATE_TOLERANCE),--decimate-tolerance $(LOTTIE_DECIMATE_TOLERANCE)) \
                    $(if $(LOTTIE_RIGID_TOLERANCE),--rigid-transform-tolerance $(LOTTIE_RIGID_TOLERANCE))
out/lottie/%.json: moho2lottie.py moho2svg.py Makefile $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	mkdir -p out/lottie
	@src="$$(ls moho/$*.animeproj moho/$*.mohoproj 2>/dev/null | head -1)"; \
	if test -z "$$src"; then echo "no source project under moho/ for $@"; exit 1; fi; \
	$(PYTHON) moho2lottie.py "$$src" --out $@ $(LOTTIE_EXPORT_FLAGS) $(lottie_size_flags) $(VALIDATE) $(image_dir_flag)

# Every project's lottie export (PROJECT_STEMS from above). A name with both
# extensions (SketchBone) exports once, through the .animeproj; a .mohoproj
# sharing that stem has no lottie export of its own.
lottie-all: $(addprefix out/lottie/,$(addsuffix .json,$(PROJECT_STEMS)))

# Runs the check scripts under tools/ against the lottie output of the
# sample projects - see their own docstrings for what each actually checks
# and why none of them needs a Lottie player or a third-party package.
#
# The geometry check gets the SAME $(LOTTIE_EXPORT_FLAGS) the export above
# used, because those flags change geometry; passing them here is what makes
# this a check of the writer rather than a diff of two different renders.
#
# check_lottie_stability.py is the one check here that does NOT compare against
# the pipeline, and that is the point: check_lottie_geometry.py compares the
# writer with the same pipeline that fed it, so it is blind to any wrong
# decision the two sides share - which is how a whole class of defect (a
# resampled loop whose vertex ring slipped, making shapes visibly spin in a
# player) shipped past a green `make check-lottie`. The stability check reads
# the emitted file alone and asks whether its keyframes can be interpolated.
#
# check_tolerance_flag mirrors whatever LOTTIE_DECIMATE_TOLERANCE the export
# above used (2.0px by default, same variable) as check_lottie_geometry.py's
# own --tolerance, or it fails on the size/accuracy trade-off
# --decimate-tolerance was asked to make - exactly the LOTTIE_EXPORT_FLAGS
# drift this target's own comment above already warns about. Set
# LOTTIE_DECIMATE_TOLERANCE= (empty) for a byte-exact export AND an exact
# (3e-3px) check together. See tools/check_lottie_geometry.py's own
# --tolerance= (note the "=": unlike --decimate-tolerance, that script does
# not consume a separate argv token for the number, so passing this as a
# plain space-separated flag would misparse the number as a frame). Reads
# LOTTIE_DECIMATE_TOLERANCE alone, not LOTTIE_RIGID_TOLERANCE too - the
# rigid-transform path is verified exact by construction
# (LottieExporter._rigid_ks_for_acc never returns a fit outside its own
# tolerance), so it does not need extra check slack the way a deliberately
# lossy decimation does.
check_tolerance_flag = $(if $(LOTTIE_DECIMATE_TOLERANCE),--tolerance=$(LOTTIE_DECIMATE_TOLERANCE))
check-lottie: out/lottie/Bandit.json out/lottie/SketchBone.json out/lottie/WhatIsBone.json
	$(PYTHON) tools/check_bezier_roundtrip.py
	$(PYTHON) tools/check_lottie_geometry.py moho/Bandit.mohoproj out/lottie/Bandit.json 25 60 100 127 --require-masks $(LOTTIE_EXPORT_FLAGS) $(check_tolerance_flag)
	$(PYTHON) tools/check_lottie_geometry.py moho/SketchBone.animeproj out/lottie/SketchBone.json 1 77 86 120 --require-gradients $(LOTTIE_EXPORT_FLAGS) $(check_tolerance_flag)
	$(PYTHON) tools/check_lottie_geometry.py moho/WhatIsBone.animeproj out/lottie/WhatIsBone.json 1 120 240 --require-masks --require-gradients $(LOTTIE_EXPORT_FLAGS) $(check_tolerance_flag)
	$(PYTHON) tools/check_lottie_stability.py out/lottie/Bandit.json out/lottie/SketchBone.json out/lottie/WhatIsBone.json

# Compares this exporter's own geometry against the frames MOHO ITSELF
# exported, which is the only ground truth in the repository - see the
# script's docstring for what it measures and why the tolerances are what
# they are. Reads three gitignored reference sets under moho/track/ -
# Bandit/svg/ (103 frames), SketchBone/new/ (120) and BoneDynamics/ (29) -
# and skips any that is absent rather than failing.
check-reference:
	$(PYTHON) tools/check_reference_frames.py

# Pretty-print the project under moho/ matching the target stem to a .json
# file - format one with e.g. `make format/moho/Bandit` (writes
# moho/Bandit.json), or `make format` for every project. The output stays
# in moho/, which is gitignored.
format: $(addprefix format/moho/,$(PROJECT_STEMS))

format/moho/%: $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	@src="$$(ls moho/$*.animeproj moho/$*.mohoproj 2>/dev/null | head -1)"; \
	if test -z "$$src"; then echo "no source project under moho/ for $@"; exit 1; fi; \
	jq . "$$src" > "moho/$*.json" && echo "wrote moho/$*.json"
