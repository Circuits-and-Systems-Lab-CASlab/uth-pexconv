#!/usr/bin/python
import os

# fastercap_panel_io.py
#
# Each of these writes a small text file describing one face (bottom/side/top)
# of a rectangular box (dielectric slab or wire), as a set of quadrilateral
# ("Q ...") panels in FasterCap's native panel format. Box corners are always
# defined locally (0,0,0) to (width, thickness, height); the actual position
# offset is supplied separately when the panel is referenced from the main
# .lst file via insert_dielectric_into_pattern_file / insert_conductor_into_pattern_file.
#
# KT-NOTE: `filename` here is a path like "Dielectrics/xxx.txt" or "Wires/xxx.txt",
# relative to `currentpath` - NOT relative to the current working directory.

def write_dielectric_side_panels(currentpath: str, filename: str, name: str, width: float, thickness: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}x{}um box\n".format(str(width), str(thickness), str(height)))
  file.write("* Layer of Box Dielectric {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write dielectric fases #
  p000 = [0.0, 0.0, 0.0]
  p001 = [0.0, 0.0, height]
  p010 = [0.0, thickness, 0.0]
  p011 = [0.0, thickness, height]

  p100 = [width, 0.0, 0.0]
  p101 = [width, 0.0, height]
  p110 = [width, thickness, 0.0]
  p111 = [width, thickness, height]

  file.write("Q dielectric_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p000[0], p000[1], p000[2], p010[0], p010[1], p010[2], p110[0], p110[1], p110[2], p100[0], p100[1], p100[2])) # front face #
  file.write("Q dielectric_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p000[0], p000[1], p000[2], p001[0], p001[1], p001[2], p011[0], p011[1], p011[2], p010[0], p010[1], p010[2])) # left fase #
  file.write("Q dielectric_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p100[0], p100[1], p100[2], p101[0], p101[1], p101[2], p111[0], p111[1], p111[2], p110[0], p110[1], p110[2])) # right fase #
  file.write("Q dielectric_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p001[0], p001[1], p001[2], p011[0], p011[1], p011[2], p111[0], p111[1], p111[2], p101[0], p101[1], p101[2])) # back face #

  file.close()

def write_dielectric_bottom_panel(currentpath: str, filename: str, name: str, width: float, thickness: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}x{}um box\n".format(str(width), str(thickness), str(height)))
  file.write("* Layer of Box Dielectric {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write dielectric fases #
  p000 = [0.0, 0.0, 0.0]
  p001 = [0.0, 0.0, height]
  p010 = [0.0, thickness, 0.0]
  p011 = [0.0, thickness, height]

  p100 = [width, 0.0, 0.0]
  p101 = [width, 0.0, height]
  p110 = [width, thickness, 0.0]
  p111 = [width, thickness, height]

  file.write("Q dielectric_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p000[0], p000[1], p000[2], p100[0], p100[1], p100[2], p101[0], p101[1], p101[2], p001[0], p001[1], p001[2])) # down face #

  file.close()

def write_dielectric_top_panel(currentpath: str, filename: str, name: str, width: float, thickness: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}x{}um box\n".format(str(width), str(thickness), str(height)))
  file.write("* Layer of Box Dielectric {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write dielectric fases #
  p000 = [0.0, 0.0, 0.0]
  p001 = [0.0, 0.0, height]
  p010 = [0.0, thickness, 0.0]
  p011 = [0.0, thickness, height]

  p100 = [width, 0.0, 0.0]
  p101 = [width, 0.0, height]
  p110 = [width, thickness, 0.0]
  p111 = [width, thickness, height]

  file.write("Q dielectric_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p010[0], p010[1], p010[2], p110[0], p110[1], p110[2], p111[0], p111[1], p111[2], p011[0], p011[1], p011[2])) # upper face #

  file.close()

def write_dielectric_side_panels_2D(currentpath: str, filename: str, name: str, width: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}um box\n".format(str(width), str(height)))
  file.write("* Layer of Box Dielectric {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  p0 = [width, 0.0]
  p1 = [width, height]

  file.write("* right face\n")
  file.write("S wire_{}  {} {}     {} {}    \n".format(name,  p0[0], p0[1], p1[0], p1[1])) # right face #

  p0 = [0.0, 0.0]
  p1 = [0.0, height]

  file.write("* left face\n")
  file.write("S dielectric_{}  {} {}     {} {}    \n".format(name,  p0[0], p0[1], p1[0], p1[1])) # left face #

  file.close()

def write_dielectric_bottom_panel_2D(currentpath: str, filename: str, name: str, width: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}um box\n".format(str(width), str(height)))
  file.write("* Layer of Box Dielectric {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write dielectric fases #
  p0 = [0.0, 0.0]
  p1 = [width, 0.0]

  file.write("* bottom face\n")

  file.write("S dielectric_{}  {} {}     {} {}\n".format(name, p0[0], p0[1], p1[0], p1[1])) # down face #

  file.close()

def write_dielectric_top_panel_2D(currentpath: str, filename: str, name: str, width: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}um box\n".format(str(width), str(height)))
  file.write("* Layer of Box Dielectric {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  p0 = [0.0, height]
  p1 = [width, height]

  file.write("* top face\n")
  file.write("S dielectric_{}  {} {}     {} {}    \n".format(name,  p0[0], p0[1], p1[0], p1[1])) # upper face #

  file.close()

def write_wire_side_panels(currentpath: str, filename: str, name: str, width: float, thickness: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}x{}um box\n".format(str(width), str(thickness), str(height)))
  file.write("* Layer of Box wire {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write wire fases #
  p000 = [0.0, 0.0, 0.0]
  p001 = [0.0, 0.0, height]
  p010 = [0.0, thickness, 0.0]
  p011 = [0.0, thickness, height]

  p100 = [width, 0.0, 0.0]
  p101 = [width, 0.0, height]
  p110 = [width, thickness, 0.0]
  p111 = [width, thickness, height]

  file.write("Q wire_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p000[0], p000[1], p000[2], p010[0], p010[1], p010[2], p110[0], p110[1], p110[2], p100[0], p100[1], p100[2])) # front face #
  file.write("Q wire_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p000[0], p000[1], p000[2], p001[0], p001[1], p001[2], p011[0], p011[1], p011[2], p010[0], p010[1], p010[2])) # left fase #
  file.write("Q wire_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p100[0], p100[1], p100[2], p101[0], p101[1], p101[2], p111[0], p111[1], p111[2], p110[0], p110[1], p110[2])) # right fase #
  file.write("Q wire_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p001[0], p001[1], p001[2], p011[0], p011[1], p011[2], p111[0], p111[1], p111[2], p101[0], p101[1], p101[2])) # back face #

  file.close()

def write_wire_side_panels_2D(currentpath: str, filename: str, name: str, width: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}um box\n".format(str(width), str(height)))
  file.write("* Layer of Box wire {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  p0 = [width, 0.0]
  p1 = [width, height]

  file.write("* right face\n")
  file.write("S wire_{}  {} {}     {} {}    \n".format(name,  p0[0], p0[1], p1[0], p1[1])) # right face #

  p0 = [0.0, 0.0]
  p1 = [0.0, height]

  file.write("* left face\n")
  file.write("S wire_{}  {} {}     {} {}    \n".format(name,  p0[0], p0[1], p1[0], p1[1])) # left face #

  file.close()

def write_wire_bottom_panel(currentpath: str, filename: str, name: str, width: float, thickness: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}x{}um box\n".format(str(width), str(thickness), str(height)))
  file.write("* Layer of Box wire {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write wire fases #
  p000 = [0.0, 0.0, 0.0]
  p001 = [0.0, 0.0, height]
  p010 = [0.0, thickness, 0.0]
  p011 = [0.0, thickness, height]

  p100 = [width, 0.0, 0.0]
  p101 = [width, 0.0, height]
  p110 = [width, thickness, 0.0]
  p111 = [width, thickness, height]

  file.write("Q wire_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p000[0], p000[1], p000[2], p100[0], p100[1], p100[2], p101[0], p101[1], p101[2], p001[0], p001[1], p001[2])) # down face #

  file.close()

def write_wire_bottom_panel_2D(currentpath: str, filename: str, name: str, width: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}um box\n".format(str(width), str(height)))
  file.write("* Layer of Box wire {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  p0 = [0.0, 0.0]
  p1 = [width, 0.0]

  file.write("* bottom face\n")

  file.write("S wire_{}  {} {}     {} {}\n".format(name, p0[0], p0[1], p1[0], p1[1])) # down face #

  file.close()

def write_wire_top_panel_2D(currentpath: str, filename: str, name: str, width: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}um box\n".format(str(width), str(height)))
  file.write("* Layer of Box wire {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  p0 = [0.0, height]
  p1 = [width, height]

  file.write("* top face\n")
  file.write("S wire_{}  {} {}     {} {}    \n".format(name,  p0[0], p0[1], p1[0], p1[1])) # upper face #

  file.close()

def write_wire_top_panel(currentpath: str, filename: str, name: str, width: float, thickness: float, height: float):
  file = open(os.path.join(currentpath, filename), "w+")

  # Write File Headers #
  file.write("* {}x{}x{}um box\n".format(str(width), str(thickness), str(height)))
  file.write("* Layer of Box wire {}\n".format(str(name)))
  file.write("* face name	| four coordinates of one face\n\n")

  # Write wire fases #
  p000 = [0.0, 0.0, 0.0]
  p001 = [0.0, 0.0, height]
  p010 = [0.0, thickness, 0.0]
  p011 = [0.0, thickness, height]

  p100 = [width, 0.0, 0.0]
  p101 = [width, 0.0, height]
  p110 = [width, thickness, 0.0]
  p111 = [width, thickness, height]

  file.write("Q wire_{}  {} {} {}     {} {} {}     {} {} {}     {} {} {}\n".format(name,  p010[0], p010[1], p010[2], p110[0], p110[1], p110[2], p111[0], p111[1], p111[2], p011[0], p011[1], p011[2])) # upper face #

  file.close()

def insert_dielectric_into_pattern_file(currentpath: str, fastercapfile, dielectricfilename, outperdiel, inperdiel, offx, offy, offz, refx, refy, refz):
  # Emit a "D" (dielectric) record in the FasterCap .lst file, referencing a
  # previously-written panel geometry file, with outer/inner permittivity,
  # the physical offset to place the panel at, and a reference point used by
  # FasterCap to determine which side is "outside" vs "inside".
  fastercapfile.write("D {}/{}   {} {}   {} {} {}    {} {} {} -  \n".format(currentpath, dielectricfilename, outperdiel, inperdiel, offx, offy, offz, refx, refy, refz))

def insert_dielectric_into_pattern_file_2D(currentpath: str, fastercapfile, dielectricfilename, outperdiel, inperdiel, offx, offy, refx, refy):
  # 2D counterpart of insert_dielectric_into_pattern_file (no z axis).
  fastercapfile.write("D {}/{}   {} {}   {} {}    {} {} -  \n".format(currentpath, dielectricfilename, outperdiel, inperdiel, offx, offy, refx, refy))

def insert_conductor_into_pattern_file_2D(currentpath: str, fastercapfile, conductorfilename, diel, refx, refy):
  # Emit a "C" (conductor) record in the FasterCap .lst file for a 2D panel.
  # Note: no trailing newline here - callers append additional text
  # (e.g. " + \n" for continuation, or "\n\n" to close the block).
  fastercapfile.write("C {}/{}   {}    {} {} ".format(currentpath, conductorfilename,  diel, refx, refy))

def insert_conductor_into_pattern_file(currentpath: str, fastercapfile, conductorfilename, diel, refx, refy, refz):
  # 3D counterpart of insert_conductor_into_pattern_file_2D.
  fastercapfile.write("C {}/{}   {}    {} {} {} ".format(currentpath, conductorfilename,  diel, refx, refy, refz))