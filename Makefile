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
	@echo '  make check-lottie                      verify lottie output (no player needed)'
	@echo '  make check-reference                   compare geometry vs Moho 14.4 exports'
	@echo '  make format                            pretty-print every moho/ project'
	@echo ''
	@echo 'Single-file targets (build any project by name):'
	@echo '  make out/svg/ori/Bandit.svg            one original export (full brush texture)'
	@echo '  make out/svg/med/SketchBone.svg        one medium-density preview'
	@echo '  make out/svg/fast/WhatIsBone.svg       one fast preview (no brush stamping)'
	@echo '  make out/svg/ori/png/SketchBone.png    render one ori SVG to PNG (3x)'
	@echo '  make out/lottie/Bandit.json            one lottie export'
	@echo '  make format/moho/Bandit                pretty-print one project (moho/Bandit.json)'
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

# Define the shared recipe bits once. $(1) is the output file; the input is
# found by `ls`, mirroring the wildcard prerequisite order above. `$*` is the
# pattern stem (expanded when the recipe runs, so it is the current target's
# own stem); `$$` are escaped dollars the shell will see.
define export_svg_recipe
	mkdir -p $(dir $(1))
	@src="$$(ls moho/$*.animeproj moho/$*.mohoproj 2>/dev/null | head -1)"; \
	if test -z "$$src"; then echo "no source project under moho/ for $(1)"; exit 1; fi; \
	python3 moho2svg.py "$$src" --combined $(1) $(2)
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
VALIDATE ?=
out/lottie/%.json: moho2lottie.py moho2svg.py Makefile $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	mkdir -p out/lottie
	@src="$$(ls moho/$*.animeproj moho/$*.mohoproj 2>/dev/null | head -1)"; \
	if test -z "$$src"; then echo "no source project under moho/ for $@"; exit 1; fi; \
	python3 moho2lottie.py "$$src" --out $@ $(VALIDATE)

# Every project's lottie export (PROJECT_STEMS from above). A name with both
# extensions (SketchBone) exports once, through the .animeproj; a .mohoproj
# sharing that stem has no lottie export of its own.
lottie-all: $(addprefix out/lottie/,$(addsuffix .json,$(PROJECT_STEMS)))

# Runs both check scripts under tools/ against the lottie output of the
# sample projects - see their own docstrings for what each actually checks
# and why neither needs a Lottie player or a third-party package.
check-lottie: out/lottie/Bandit.json out/lottie/SketchBone.json out/lottie/WhatIsBone.json
	python3 tools/check_bezier_roundtrip.py
	python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj out/lottie/Bandit.json 25 60 100 127 --require-masks
	python3 tools/check_lottie_geometry.py moho/SketchBone.animeproj out/lottie/SketchBone.json 1 77 86 120 --require-gradients
	python3 tools/check_lottie_geometry.py moho/WhatIsBone.animeproj out/lottie/WhatIsBone.json 1 120 240 --require-masks --require-gradients

# Compares this exporter's own geometry against the frames MOHO ITSELF
# exported, which is the only ground truth in the repository - see the
# script's docstring for what it measures and why the tolerances are what
# they are. Reads three gitignored reference sets under moho/track/ -
# Bandit/svg/ (103 frames), SketchBone/new/ (120) and BoneDynamics/ (29) -
# and skips any that is absent rather than failing.
check-reference:
	python3 tools/check_reference_frames.py

# Pretty-print the project under moho/ matching the target stem to a .json
# file - format one with e.g. `make format/moho/Bandit` (writes
# moho/Bandit.json), or `make format` for every project. The output stays
# in moho/, which is gitignored.
format: $(addprefix format/moho/,$(PROJECT_STEMS))

format/moho/%: $$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)
	@src="$$(ls moho/$*.animeproj moho/$*.mohoproj 2>/dev/null | head -1)"; \
	if test -z "$$src"; then echo "no source project under moho/ for $@"; exit 1; fi; \
	jq . "$$src" > "moho/$*.json" && echo "wrote moho/$*.json"
