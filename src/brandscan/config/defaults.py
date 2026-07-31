"""Seeded search-groups and scope defaults.

The seven seeded groups are ordinary groups, not privileged built-ins: the
loader lets configuration edit or remove any of them, and a user-defined group
runs through exactly the same engine.
"""

from __future__ import annotations

import re

from brandscan.config.model import ImageScope, ScanScope, SearchGroup, Severity

# Third-party code. Its branding is not ours to change.
DEFAULT_EXCLUDE_DIRS = [
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "bower_components",
    "vendor",
    "packages",
    "venv",
    ".venv",
    "env",
    "site-packages",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    ".gradle",
    ".idea",
    ".vs",
]

# Deliberately absent from the exclusions above: dist, build, out, wwwroot,
# bin, obj, target, public. Deployed brand assets frequently exist *only* in
# build output, and this estate checks build output in. Excluding it would
# create a silent miss of exactly the assets that actually ship. The cost is
# duplicate findings between source and build output, which is cheap to
# dismiss; a confident miss is not.
BUILD_OUTPUT_DIRS_NOT_EXCLUDED = [
    "dist",
    "build",
    "out",
    "bin",
    "obj",
    "target",
    "wwwroot",
    "public",
    "_site",
]

DEFAULT_EXCLUDE_GLOBS = [
    "*.min.map",
    "*.pdb",
    "*.zip",
    "*.gz",
    "*.7z",
    "*.tar",
    "*.exe",
    "*.dll",
    "*.mp4",
    "*.mov",
]

FONT_FILE_EXTENSIONS = ["woff2", "woff", "ttf", "otf", "eot"]

EXTERNAL_FONT_SERVICES = [
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "use.typekit.net",
    "p.typekit.net",
    "fast.fonts.net",
    "cloud.typography.com",
    "use.fontawesome.com",
]

# Everything a URL can carry after the host, stopping at whatever would end the
# link in markup or a stylesheet. Both attribution and exclusion read the text a
# pattern matched, so a pattern stopping at the host would hide the family name
# from both — every `?family=` link would be unattributable regardless of what
# it actually requests.
URL_TAIL = r"[^\s\"'<>)]*"

# Third-party icon and font packages. Their branding is not ours to change, and
# a filename pattern only ever proved that a font file exists at a path — never
# anything about its glyphs — so vetoing them suppresses no evidence the pattern
# was actually providing. Applied to `unattributed-font-assets` alone: a file
# called `fa-contoso-sans-400.woff2` is attributed to the brand before this list
# is ever consulted. It is seeded config, so `exclude_matches: []` on the group
# restores the full inventory in one line.
VENDOR_FONT_PACKAGES = [
    r"glyphicons",
    r"font[\s_\-]?awesome",
    r"\bfa[\-_](?:brands|solid|regular|light|thin|duotone|v4compatibility)\b",
    r"bootstrap[\s_\-]?icons",
    r"material[\s_\-]?(?:icons|symbols)",
    r"ionicons",
    r"octicons",
    r"feather[\s_\-]?icons",
    r"simple[\s_\-]?line[\s_\-]?icons",
    r"typicons",
    r"elusive[\s_\-]?icons",
]

TEXT_LIKE_GLOBS = [
    "*.cs", "*.vb", "*.aspx", "*.ascx", "*.ashx", "*.asax", "*.cshtml", "*.vbhtml",
    "*.html", "*.htm", "*.xhtml", "*.xml", "*.xaml", "*.svg", "*.md", "*.txt",
    "*.css", "*.scss", "*.sass", "*.less", "*.styl",
    "*.js", "*.jsx", "*.ts", "*.tsx", "*.vue", "*.svelte",
    "*.json", "*.yaml", "*.yml", "*.toml", "*.ini", "*.config", "*.props", "*.targets",
    "*.py", "*.rb", "*.php", "*.java", "*.kt", "*.go", "*.rs", "*.sql",
    "*.sh", "*.ps1", "*.bat", "*.cmd", "*.resx", "*.plist", "*.csproj", "*.sln",
]

STYLE_AND_MARKUP_GLOBS = [
    "*.css", "*.scss", "*.sass", "*.less", "*.styl",
    "*.html", "*.htm", "*.xhtml", "*.aspx", "*.ascx", "*.cshtml", "*.vbhtml",
    "*.svg", "*.xaml", "*.js", "*.jsx", "*.ts", "*.tsx", "*.vue", "*.svelte",
]


# The one class of brand asset that is legitimately tiny. At the default
# minimum these clear it unaided — a favicon is 16x16 and the minimum is 15.
# The exemption exists so the minimum stays tunable *upward*: raising it to 32
# after a run turns up a pile of 20x20 sprite fragments would otherwise drop
# every favicon in the estate in the same edit, silently, and a favicon is the
# brand in the browser tab of every deployed site.
DEFAULT_ALWAYS_EXAMINE_GLOBS = [
    "favicon*",
    "apple-touch-icon*",
    "*.ico",
    "*.cur",
]


def default_scope() -> ScanScope:
    return ScanScope(
        exclude_dirs=list(DEFAULT_EXCLUDE_DIRS),
        exclude_globs=list(DEFAULT_EXCLUDE_GLOBS),
        include_globs=[],
    )


def default_image_scope() -> ImageScope:
    return ImageScope(always_examine=list(DEFAULT_ALWAYS_EXAMINE_GLOBS))


def flexible_name_pattern(name: str) -> str:
    """A brand name as it appears in prose *and* in identifiers.

    "Contoso Ltd" is written `Contoso Ltd` in body text, `contoso-ltd` in a CSS
    class, `contosoLtd` in code, and `contoso_ltd` in a resource key. Allowing
    an optional separator between the words catches all of them from one
    configured value.

    No word boundary is required around the whole match: brand references hide
    inside compound identifiers (`contosoHeaderLogo`) and inside markup
    attributes (`alt="Our Contoso logo"`, `class="contoso-brand"`,
    `<title>Contoso</title>`), and a rebrand needs those far more than it needs
    the precision a boundary would buy.
    """
    words = [re.escape(word) for word in name.split()]
    return r"[\s_\-]*".join(words)


def url_font_pattern(name: str) -> str:
    """A font name as it appears inside a font-service URL.

    A query string spells the space as `+` or `%20` —
    `fonts.googleapis.com/css?family=Contoso+Sans` — so the prose spelling alone
    would miss every multi-word brand font on the service that hosts most of
    them.
    """
    words = [re.escape(word) for word in name.split()]
    return r"(?:[\s_\-+]|%20)*".join(words)


def seed_default_groups(
    names: list[str],
    fonts: list[str],
    domains: list[str],
    colors: list[str],
    legal: list[str],
) -> list[SearchGroup]:
    """Build the seven seeded groups from the configured brand vocabulary."""
    name_patterns = [flexible_name_pattern(n) for n in names]
    font_patterns = [flexible_name_pattern(f) for f in fonts]
    domain_patterns = [re.escape(d).replace(r"\.", r"\.") for d in domains]
    legal_patterns = [flexible_name_pattern(entry) for entry in legal]

    font_extensions = "|".join(FONT_FILE_EXTENSIONS)
    # A font asset whose own reference names a configured brand font. The same
    # `flexible_name_pattern` expansion `font-names` uses, so the two font
    # groups cannot drift in what they consider the brand's font.
    attributed_font_patterns = [
        *[rf"[\w\-./]*{p}[\w\-./]*\.(?:{font_extensions})\b" for p in font_patterns],
        *[
            rf"{re.escape(service)}{URL_TAIL}{url_font_pattern(f)}{URL_TAIL}"
            for service in EXTERNAL_FONT_SERVICES
            for f in fonts
        ],
    ]
    # Any font asset at all — the miss-averse catch-all. Deliberately broader
    # than the attributed patterns: a brand font file frequently carries no
    # brand string in its name (`NS-Bold.woff2`), and this is the only place
    # such a file can surface.
    any_font_patterns = [
        rf"[\w\-./]+\.(?:{font_extensions})\b",
        *[rf"{re.escape(service)}{URL_TAIL}" for service in EXTERNAL_FONT_SERVICES],
    ]

    groups: list[SearchGroup] = []

    groups.append(
        SearchGroup(
            name="brand-names",
            patterns=name_patterns,
            severity=Severity.MEDIUM,
            description=(
                "Occurrences of the old brand name in prose, code, and markup "
                "(image alt attributes, CSS class and identifier names, SVG "
                "title and description elements)."
            ),
            remediation=(
                "Replace the old brand name with the new one. Where the name is "
                "part of a CSS class, identifier, or resource key, rename it and "
                "update every reference to it."
            ),
        )
    )

    groups.append(
        SearchGroup(
            name="font-names",
            patterns=[
                *[rf"font-family\s*:[^;{{}}]*{p}" for p in font_patterns],
                *[rf"@font-face[^}}]*{p}" for p in font_patterns],
                *[rf"\bFontFamily\s*=\s*[\"'][^\"']*{p}" for p in font_patterns],
                *font_patterns,
            ],
            include=list(STYLE_AND_MARKUP_GLOBS) + ["*.xaml", "*.resx", "*.json"],
            severity=Severity.MEDIUM,
            description="Brand fonts named in font-family or font-face declarations.",
            remediation=(
                "Swap the declared font for the new brand font and confirm the "
                "replacement is actually loaded, not just named."
            ),
        )
    )

    groups.append(
        SearchGroup(
            name="font-references",
            patterns=attributed_font_patterns,
            severity=Severity.MEDIUM,
            description=(
                "Font assets — embedded font files and links to externally "
                "hosted font services — whose reference names a configured "
                "brand font."
            ),
            remediation=(
                "Remove or replace the referenced font asset with the new brand "
                "font, and confirm the replacement is actually loaded rather "
                "than merely named."
            ),
        )
    )

    groups.append(
        SearchGroup(
            name="unattributed-font-assets",
            patterns=any_font_patterns,
            # Anything the attributed group already reports, so one reference
            # never surfaces as both a brand finding and an inventory item.
            exclude_matches=[*attributed_font_patterns, *VENDOR_FONT_PACKAGES],
            severity=Severity.LOW,
            description=(
                "Font assets the scan found but could not tie to a configured "
                "brand font. This is an inventory for triage, not a brand "
                "match: a brand font file frequently carries no brand string in "
                "its name, so it can only surface here."
            ),
            remediation=(
                "Establish whether the family is a brand font before acting — "
                "read the font's own metadata, or the declaration that loads "
                "it. Replace it only once you have confirmed it is the old "
                "brand's; leave third-party package fonts alone."
            ),
        )
    )

    groups.append(
        SearchGroup(
            name="legacy-domains",
            patterns=[
                *[rf"(?:https?://)?(?:[\w\-]+\.)*{p}(?:/[^\s\"'<>)]*)?" for p in domain_patterns],
            ],
            severity=Severity.MEDIUM,
            description="Legacy brand domains and URLs on them.",
            remediation=(
                "Repoint the URL at the new domain. Check for redirects rather "
                "than assuming the path survives the move."
            ),
        )
    )

    groups.append(
        SearchGroup(
            name="brand-colours",
            colors=list(colors),
            severity=Severity.LOW,
            description=(
                "Brand colours in any equivalent notation — hexadecimal, "
                "shorthand hexadecimal, and functional rgb()/rgba() forms."
            ),
            remediation=(
                "Replace with the new palette value. Prefer introducing a named "
                "token over substituting another literal."
            ),
        )
    )

    groups.append(
        SearchGroup(
            name="legal-strings",
            patterns=[
                *legal_patterns,
                *[rf"(?:©|\(c\)|Copyright)[^\n]{{0,40}}{p}" for p in name_patterns],
                *[rf"{p}\s*(?:™|®|\(tm\)|\(r\))" for p in name_patterns],
            ],
            severity=Severity.MEDIUM,
            description=(
                "Legal entity names, copyright notices, and trademark markers "
                "carrying the old brand."
            ),
            remediation=(
                "Update to the current legal entity and notice wording. Legal "
                "text usually needs sign-off rather than a direct substitution."
            ),
        )
    )

    return groups
