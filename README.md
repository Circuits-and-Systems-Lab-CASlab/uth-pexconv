# UTH-pexconv

Converters and tooling bridging parasitic-extraction pattern formats
(OpenRCX's Universal Format, and the [C25D format](https://github.com/iic-jku/klayout-pex/issues/184))
to multiple field solver back-ends (FasterCap, and others planned).
Developed as part of the ODE4EC-AMS project.

## Status

Code under development. Interfaces and supported features may change.
C25D support currently covers `GROUND_PLANE`, `METAL`/`VIA`,
`DIELECTRIC_BACKGROUND`, `CONDUCTOR`/`BOX`, and `DOMAIN_MARGIN`/`DOMAIN_BOX`.

`DIELECTRIC_SIMPLE`/`SIDEWALL`/`CONFORMAL` and `POLYGON` are not yet
supported.

## Repository structure

```
UTH-pexconv/
├── converters/                 Format converters: Universal Format & C25D to field solver backends
│   ├── common/                 Shared code: C25D parser, domain resolution
│   └── fastercap/               universal/C25D-to-FasterCap converter
├── docs/                       Universal Format documentation
├── examples/
│   └── fastercap-conversion/   End-to-end conversion + FasterCap solver run scripts
├── external/
│   ├── openroad/                OpenROAD (git submodule)
│   └── openroad-patterns/       Wrapper around OpenROAD's gen_solver_patterns,
│                                 using this repo's paths instead of OpenROAD's own
├── .gitignore
├── .gitmodules
├── LICENSE
└── README.md
```

## Testing

Both converter pipelines have pytest suites:

```bash
cd converters/fastercap && pytest tests/
cd converters/common && pytest tests/
```

## Funding acknowledgement

This work is developed by the [University of Thessaly](https://www.uth.gr/en)'s [Circuits and
Systems (CAS) Lab](https://caslab.e-ce.uth.gr/), as part of the
**ODE4EC-AMS** project, funded through the [Chips Joint Undertaking (Chips JU)](https://www.chips-ju.europa.eu/).

<p align="center">
  <img src="https://caslab.e-ce.uth.gr/img/logo/logo_new.png" alt="CASLab logo" height="80">
  <img src="https://www.uth.gr/sites/default/files/contents/logos/UTH-logo-english.png" alt="University of Thessaly logo" height="80">
  <img src="https://caslab.e-ce.uth.gr/img/rnd/AMS.png" alt="ODE4EC-AMS logo" height="80">
</p>

## Acknowledgements

Field solver pattern generation builds on
[OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) and OpenRCX.