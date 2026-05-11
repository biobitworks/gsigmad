# gsigmad Homebrew Tap

## Installation

    brew tap biobitworks/gsigmad
    brew install gsigmad

## Publishing Checklist

1. Publish gsigmad to PyPI: `python -m build && twine upload dist/*`
2. Generate resource stanzas: `pip install homebrew-pypi-poet && poet gsigmad`
3. Update gsigmad.rb with actual URL, sha256, and resource stanzas
4. Create the tap repo: https://github.com/biobitworks/homebrew-gsigmad
5. Copy gsigmad.rb to Formula/ in the tap repo
6. Test: `brew audit --new-formula gsigmad && brew test gsigmad`
