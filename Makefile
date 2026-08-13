gen:
	mkdir -p svg
	python3 moho2svg.py moho/Bandit.mohoproj --combined svg/Bandit.svg
	python3 moho2svg.py moho/WhatIsBone.animeproj --combined svg/WhatIsBone.svg
	python3 moho2svg.py moho/AddBone.animeproj --combined svg/AddBone.svg
	python3 moho2svg.py moho/ReparentBone.animeproj --combined svg/ReparentBone.svg
	python3 moho2svg.py moho/SketchBone.animeproj --combined svg/SketchBone.svg

styles.brushes:
	ln -s /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/Brushes

format:
	jq . moho/AddBone.animeproj > moho/AddBone.pretty.json
	jq . moho/Bandit.mohoproj > moho/Bandit.pretty.json
	jq . moho/ReparentBone.animeproj > moho/ReparentBone.pretty.json
	jq . moho/SketchBone.animeproj > moho/SketchBone.pretty.json
	jq . moho/WhatIsBone.animeproj > moho/WhatIsBone.pretty.json
