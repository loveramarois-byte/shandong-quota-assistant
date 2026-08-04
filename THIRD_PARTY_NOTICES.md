# Third-Party Notices

The MIT License in this repository applies to the original application code.
It does not relicense third-party components.

## Bundled font

Inter font files are included under the SIL Open Font License 1.1.

- Project: https://github.com/rsms/inter
- Copyright: 2016 The Inter Project Authors
- License text: [assets/fonts/LICENSE.txt](assets/fonts/LICENSE.txt)

Noto Sans SC is bundled as the Simplified Chinese fallback font under the SIL
Open Font License 1.1.

- Project: https://github.com/notofonts/noto-cjk
- Copyright: 2014-2021 Adobe and Google
- License text: [assets/fonts/NotoSansSC-LICENSE.txt](assets/fonts/NotoSansSC-LICENSE.txt)

Source Han Serif SC is bundled as the Simplified Chinese display font under
the SIL Open Font License 1.1. It is used for editorial headings while body
copy remains in the sans-serif UI stack.

- Project: https://github.com/adobe-fonts/source-han-serif
- Copyright: 2017-2022 Adobe
- License text: [assets/fonts/SourceHanSerifSC-LICENSE.txt](assets/fonts/SourceHanSerifSC-LICENSE.txt)

## Runtime and build dependencies

Packages listed in `requirements.txt` are installed from their respective
distributions and remain subject to their upstream license terms. They are not
vendored into this source repository. Review the package metadata before
redistributing a compiled binary.

The Qt desktop migration currently uses PyQt6. PyQt6 is available under the
GNU General Public License or a commercial license. A redistributable binary
must therefore be released under compatible GPL terms or built with a valid
commercial PyQt license; the repository's MIT notice does not replace that
requirement.

The public repository also excludes downloaded copies of 7-Zip and Inno Setup.
Packaging scripts expect developers to obtain required build tools from their
official distribution channels and comply with their own license terms.

Product and service names mentioned in compatibility documentation belong to
their respective owners. Mentioning an API compatibility target does not imply
affiliation, authorization, sponsorship, or endorsement.
