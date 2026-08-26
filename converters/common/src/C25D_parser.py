#!/usr/bin/python
import shlex

# NOT YET SUPPORTED - raises NotImplementedError, on purpose:
#   DIELECTRIC_SIDEWALL, DIELECTRIC_CONFORMAL and POLYGON shapes

class C25DParseError(Exception):
    def __init__(self, message: str, line_number: int, line_text: str):
        self.line_number = line_number
        self.line_text = line_text
        super().__init__(f"line {line_number}: {message}\n  > {line_text}")


class GroundPlane:
    def __init__(self, name: str, zlow: float, zhigh: float):
        self.name = name
        self.zlow = zlow
        self.zhigh = zhigh

    def contains_z(self, z: float) -> bool:
        return self.zlow <= z <= self.zhigh


class Layer:
    #  A METAL or VIA layer: name and a Z range. Layers, VIAs, and
    # dielectric profile names all share one namespace per the C25D spec.
    def __init__(self, name: str, kind: str, zlow: float, zhigh: float):
        self.name = name
        self.kind = kind  # "METAL" or "VIA"
        self.zlow = zlow
        self.zhigh = zhigh


class DielectricProfile:
    def __init__(self, name: str, kind: str, permittivity: float,
                 zlow: float = None, zhigh: float = None, wraps: str = None):
        self.name = name
        self.kind = kind  # "SIMPLE" or "BACKGROUND"
        self.permittivity = permittivity
        self.zlow = zlow
        self.zhigh = zhigh
        self.wraps = wraps

    def contains_z(self, z: float) -> bool:
        if self.kind == "BACKGROUND":
            return True
        return self.zlow <= z <= self.zhigh


class BoxShape:
    def __init__(self, layer_name: str, llx: float, lly: float, urx: float, ury: float):
        self.layer_name = layer_name
        self.llx = llx
        self.lly = lly
        self.urx = urx
        self.ury = ury


class Conductor:
    def __init__(self, shortname: str, net: str):
        self.shortname = shortname
        self.net = net
        self.shapes = []  # list of BoxShape (PolygonShape not in v1 scope)


class Domain:
    def __init__(self):
        self.margin = None  # (x, y, z) or None
        self.box = None     # (llx, lly, llz, urx, ury, urz) or None


class C25DScene:
    def __init__(self):
        self.version = None
        self.length_unit = None
        self.metadata = {}
        self.ground_planes = []       # list of GroundPlane
        self.layers = {}              # name -> Layer
        self.dielectrics = []         # list of DielectricProfile, in file order
        self.background = None        # the one DielectricProfile with kind="BACKGROUND"
        self.conductors = {}          # shortname -> Conductor
        self.domain = Domain()
        self._profile_names = set()   # METAL/VIA/DIELECTRIC namespace, for uniqueness checks

    def epsilon_at(self, x: float, y: float, z: float) -> float:
        candidate = None
        for dielectric in self.dielectrics:
            if dielectric.kind == "SIMPLE" and dielectric.contains_z(z):
                candidate = dielectric 
        if candidate is not None:
            return candidate.permittivity
        return self.background.permittivity

    def is_inside_ground_plane(self, z: float) -> bool:
        return any(gp.contains_z(z) for gp in self.ground_planes)


def _tokenize_line(line: str) -> list:
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _require_unique_profile_name(scene: C25DScene, name: str, line_number: int, line_text: str):
    if name in scene._profile_names:
        raise C25DParseError(
            f"name '{name}' is declared more than once "
            "(METAL, VIA, and DIELECTRIC names share one namespace)",
            line_number, line_text,
        )
    scene._profile_names.add(name)


def parse_c25d(path: str) -> C25DScene:
    scene = C25DScene()

    with open(path) as f:
        raw_lines = f.readlines()

    for line_number, raw_line in enumerate(raw_lines, start=1):
        tokens = _tokenize_line(raw_line)
        if not tokens:
            continue

        keyword = tokens[0]

        if keyword == "C25D":
            if len(tokens) != 2:
                raise C25DParseError("expected: C25D <version>", line_number, raw_line)
            scene.version = tokens[1]

        elif keyword == "UNITS":
            if len(tokens) != 3 or tokens[1] != "LENGTH":
                raise C25DParseError("expected: UNITS LENGTH <unit>", line_number, raw_line)
            scene.length_unit = tokens[2]

        elif keyword == "META":
            if len(tokens) < 3:
                raise C25DParseError("expected: META <key> <value>", line_number, raw_line)
            scene.metadata[tokens[1]] = " ".join(tokens[2:])

        elif keyword == "GROUND_PLANE":
            if len(tokens) != 5 or tokens[2] != "Z_OFFSETS":
                raise C25DParseError(
                    "expected: GROUND_PLANE <name> Z_OFFSETS <zlow> <zhigh>",
                    line_number, raw_line,
                )
            name, zlow, zhigh = tokens[1], float(tokens[3]), float(tokens[4])
            scene.ground_planes.append(GroundPlane(name, zlow, zhigh))

        elif keyword in ("METAL", "VIA"):
            if len(tokens) != 5 or tokens[2] != "Z_OFFSETS":
                raise C25DParseError(
                    f"expected: {keyword} <name> Z_OFFSETS <zlow> <zhigh>",
                    line_number, raw_line,
                )
            name, zlow, zhigh = tokens[1], float(tokens[3]), float(tokens[4])
            _require_unique_profile_name(scene, name, line_number, raw_line)
            scene.layers[name] = Layer(name, keyword, zlow, zhigh)

        elif keyword == "DIELECTRIC_SIMPLE":
            # DIELECTRIC_SIMPLE <name> Z_OFFSETS <zlow> <zhigh> PERMITTIVITY <k> WRAPS <name>
            if (len(tokens) != 9 or tokens[2] != "Z_OFFSETS"
                    or tokens[5] != "PERMITTIVITY" or tokens[7] != "WRAPS"):
                raise C25DParseError(
                    "expected: DIELECTRIC_SIMPLE <name> Z_OFFSETS <zlow> <zhigh> "
                    "PERMITTIVITY <k> WRAPS <name>",
                    line_number, raw_line,
                )
            name = tokens[1]
            zlow, zhigh = float(tokens[3]), float(tokens[4])
            permittivity = float(tokens[6])
            wraps = tokens[8]
            _require_unique_profile_name(scene, name, line_number, raw_line)
            if wraps not in scene._profile_names:
                raise C25DParseError(
                    f"WRAPS references '{wraps}', which has not been declared "
                    "(WRAPS must reference a previously-defined METAL, VIA, "
                    "or DIELECTRIC profile)",
                    line_number, raw_line,
                )
            scene.dielectrics.append(
                DielectricProfile(name, "SIMPLE", permittivity, zlow, zhigh, wraps)
            )

        elif keyword in ("DIELECTRIC_SIDEWALL", "DIELECTRIC_CONFORMAL"):
            raise NotImplementedError(
                f"line {line_number}: {keyword} is not yet supported by C25D_parser.py "
                "(v1 scope is GROUND_PLANE/METAL/VIA/DIELECTRIC_SIMPLE/"
                "DIELECTRIC_BACKGROUND/CONDUCTOR/BOX/DOMAIN_MARGIN/DOMAIN_BOX "
                "only - sidewall/conformal footprints depend on the wrapped "
                f"conductor's shape, not just a Z range).\n  > {raw_line.strip()}"
            )

        elif keyword == "DIELECTRIC_BACKGROUND":
            # DIELECTRIC_BACKGROUND <name> PERMITTIVITY <k>
            if len(tokens) != 4 or tokens[2] != "PERMITTIVITY":
                raise C25DParseError(
                    "expected: DIELECTRIC_BACKGROUND <name> PERMITTIVITY <k>",
                    line_number, raw_line,
                )
            if scene.background is not None:
                raise C25DParseError(
                    "a second DIELECTRIC_BACKGROUND was declared - exactly "
                    f"one is required (first was '{scene.background.name}')",
                    line_number, raw_line,
                )
            name = tokens[1]
            permittivity = float(tokens[3])
            _require_unique_profile_name(scene, name, line_number, raw_line)
            profile = DielectricProfile(name, "BACKGROUND", permittivity)
            scene.dielectrics.append(profile)
            scene.background = profile

        elif keyword == "CONDUCTOR":
            if len(tokens) != 3:
                raise C25DParseError(
                    "expected: CONDUCTOR <shortname> <net>", line_number, raw_line
                )
            shortname, net = tokens[1], tokens[2]
            if shortname in scene.conductors:
                raise C25DParseError(
                    f"conductor '{shortname}' is declared more than once",
                    line_number, raw_line,
                )
            scene.conductors[shortname] = Conductor(shortname, net)

        elif keyword == "BOX":
            # BOX CONDUCTOR <shortname> LAYER <layer_name> LL <x> <y> UR <x> <y>
            if (len(tokens) != 11 or tokens[1] != "CONDUCTOR" or tokens[3] != "LAYER"
                    or tokens[5] != "LL" or tokens[8] != "UR"):
                raise C25DParseError(
                    "expected: BOX CONDUCTOR <shortname> LAYER <layer_name> "
                    "LL <x> <y> UR <x> <y>",
                    line_number, raw_line,
                )
            shortname, layer_name = tokens[2], tokens[4]
            llx, lly = float(tokens[6]), float(tokens[7])
            urx, ury = float(tokens[9]), float(tokens[10])
            if shortname not in scene.conductors:
                raise C25DParseError(
                    f"BOX references conductor '{shortname}', which has not "
                    "been declared with a CONDUCTOR record",
                    line_number, raw_line,
                )
            if layer_name not in scene.layers:
                raise C25DParseError(
                    f"BOX references LAYER '{layer_name}', which has not "
                    "been declared with a METAL or VIA record",
                    line_number, raw_line,
                )
            scene.conductors[shortname].shapes.append(
                BoxShape(layer_name, llx, lly, urx, ury)
            )

        elif keyword == "POLYGON":
            raise NotImplementedError(
                f"line {line_number}: POLYGON shapes are not yet supported by "
                f"C25D_parser.py (v1 scope is BOX shapes only).\n  > {raw_line.strip()}"
            )

        elif keyword == "DOMAIN_MARGIN":
            # DOMAIN_MARGIN X <xmargin> Y <ymargin> Z <zmargin>
            if (len(tokens) != 7 or tokens[1] != "X" or tokens[3] != "Y" or tokens[5] != "Z"):
                raise C25DParseError(
                    "expected: DOMAIN_MARGIN X <xmargin> Y <ymargin> Z <zmargin>",
                    line_number, raw_line,
                )
            xmargin, ymargin, zmargin = float(tokens[2]), float(tokens[4]), float(tokens[6])
            scene.domain.margin = (xmargin, ymargin, zmargin)

        elif keyword == "DOMAIN_BOX":
            # DOMAIN_BOX LL <x> <y> <z> UR <x> <y> <z>
            if len(tokens) != 9 or tokens[1] != "LL" or tokens[5] != "UR":
                raise C25DParseError(
                    "expected: DOMAIN_BOX LL <x> <y> <z> UR <x> <y> <z>",
                    line_number, raw_line,
                )
            llx, lly, llz = float(tokens[2]), float(tokens[3]), float(tokens[4])
            urx, ury, urz = float(tokens[6]), float(tokens[7]), float(tokens[8])
            scene.domain.box = (llx, lly, llz, urx, ury, urz)

        else:
            raise C25DParseError(f"unknown keyword '{keyword}'", line_number, raw_line)

    if scene.background is None:
        raise C25DParseError(
            "no DIELECTRIC_BACKGROUND declared - exactly one is required",
            line_number=len(raw_lines), line_text="(end of file)",
        )

    return scene