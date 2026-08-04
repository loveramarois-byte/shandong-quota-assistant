# Third-Party Notices

The MIT License in this repository applies to the original application code.
It does not relicense third-party components.

## Bundled font

Inter font files are included under the SIL Open Font License 1.1.

- Project: https://github.com/rsms/inter
- Copyright: 2016 The Inter Project Authors
- License text: [assets/fonts/LICENSE.txt](assets/fonts/LICENSE.txt)

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
