gen:
	mkdir -p svg
	python3 moho2svg.py moho/Bandit.mohoproj --combined svg/Bandit.svg
	python3 moho2svg.py moho/WhatIsBone.animeproj --combined svg/WhatIsBone.svg
	python3 moho2svg.py moho/AddBone.animeproj --combined svg/AddBone.svg
	python3 moho2svg.py moho/ReparentBone.animeproj --combined svg/ReparentBone.svg
	python3 moho2svg.py moho/SketchBone.animeproj --combined svg/SketchBone.svg
