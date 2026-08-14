gen:
	mkdir -p svg
	python3 moho2svg.py moho/Bandit.mohoproj --combined svg/Bandit.svg
	python3 moho2svg.py moho/WhatIsBone.animeproj --combined svg/WhatIsBone.svg
	python3 moho2svg.py moho/AddBone.animeproj --combined svg/AddBone.svg
	python3 moho2svg.py moho/ReparentBone.animeproj --combined svg/ReparentBone.svg
	python3 moho2svg.py moho/SketchBone.animeproj --combined svg/SketchBone.svg

# Medium-density preview export: brush stamping at --brush-spacing-mul
# BRUSH_SPACING_MUL (default 2 = half the dabs of the tracked reference;
# override on the command line, e.g. `make gen-med BRUSH_SPACING_MUL=4`).
# Output goes to svg-med/, NOT svg/, so it never clobbers the tracked
# reference SVGs.
BRUSH_SPACING_MUL ?= 2
gen-med:
	mkdir -p svg-med
	python3 moho2svg.py moho/Bandit.mohoproj --combined svg-med/Bandit.svg --brush-spacing-mul $(BRUSH_SPACING_MUL)
	python3 moho2svg.py moho/WhatIsBone.animeproj --combined svg-med/WhatIsBone.svg --brush-spacing-mul $(BRUSH_SPACING_MUL)
	python3 moho2svg.py moho/AddBone.animeproj --combined svg-med/AddBone.svg --brush-spacing-mul $(BRUSH_SPACING_MUL)
	python3 moho2svg.py moho/ReparentBone.animeproj --combined svg-med/ReparentBone.svg --brush-spacing-mul $(BRUSH_SPACING_MUL)
	python3 moho2svg.py moho/SketchBone.animeproj --combined svg-med/SketchBone.svg --brush-spacing-mul $(BRUSH_SPACING_MUL)

# Fast preview export: brush stamping disabled entirely (--brush-dir ""), so
# a heavily brush-styled document (e.g. SketchBone) stays quick to open in a
# browser/SVG viewer - see docs/moho-exporting-svg.md § Brush textures. Output
# goes to svg-fast/, NOT svg/, so it never clobbers the tracked reference
# SVGs (which are meant to include brush texture).
gen-fast:
	mkdir -p svg-fast
	python3 moho2svg.py moho/Bandit.mohoproj --combined svg-fast/Bandit.svg --brush-dir ""
	python3 moho2svg.py moho/WhatIsBone.animeproj --combined svg-fast/WhatIsBone.svg --brush-dir ""
	python3 moho2svg.py moho/AddBone.animeproj --combined svg-fast/AddBone.svg --brush-dir ""
	python3 moho2svg.py moho/ReparentBone.animeproj --combined svg-fast/ReparentBone.svg --brush-dir ""
	python3 moho2svg.py moho/SketchBone.animeproj --combined svg-fast/SketchBone.svg --brush-dir ""

# Smallest/fastest brush export: each brush-styled shape's whole stroke is
# composited into ONE raster <image> at export time (--brush-raster) instead
# of one <use>/dab per stamp - biggest size/speed win of all the brush
# options, at the cost of that stroke no longer being vector (not rescalable/
# editable as a path afterwards), and a visible softening of fine/wispy
# textures under heavy dab overlap (see docs/moho-exporting-svg.md § 7 for the
# "golge" example). Requires Pillow. Output goes to svg-raster/, NOT svg/.
gen-raster:
	mkdir -p svg-raster
	python3 moho2svg.py moho/Bandit.mohoproj --combined svg-raster/Bandit.svg --brush-raster
	python3 moho2svg.py moho/WhatIsBone.animeproj --combined svg-raster/WhatIsBone.svg --brush-raster
	python3 moho2svg.py moho/AddBone.animeproj --combined svg-raster/AddBone.svg --brush-raster
	python3 moho2svg.py moho/ReparentBone.animeproj --combined svg-raster/ReparentBone.svg --brush-raster
	python3 moho2svg.py moho/SketchBone.animeproj --combined svg-raster/SketchBone.svg --brush-raster

# Render one SVG under svg/ to a PNG under svg/png/ at 3x size, e.g.:
#   make svg/png/SketchBone.png
svg/png/%.png: svg/%.svg
	rsvg-convert -z 3 -o $@ $<

styles.brushes:
	ln -s /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/Brushes

format:
	jq . moho/AddBone.animeproj > moho/AddBone.pretty.json
	jq . moho/Bandit.mohoproj > moho/Bandit.pretty.json
	jq . moho/ReparentBone.animeproj > moho/ReparentBone.pretty.json
	jq . moho/SketchBone.animeproj > moho/SketchBone.pretty.json
	jq . moho/WhatIsBone.animeproj > moho/WhatIsBone.pretty.json
