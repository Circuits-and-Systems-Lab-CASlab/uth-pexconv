#!/usr/bin/python
import os
import sys
from operator import attrgetter

import fastercap_panel_io as panel_io

# Universal2FasterCapConverter.py
#
# Converts pattern files written in the "universal" PEX format into FasterCap
# input files (.lst pattern files referencing generated panel geometry files).
#
# Supports both 2D and 3D geometry modes. For each mode, the flow is:
#   1. Parse the universal-format "wires" file into intermediate data
#      structures (UniversalFormatDielectrics*, UniversalFormatGroundPlanes*,
#      UniversalFormatWires*).
#   2. Convert those into a flat list of "Shapes" (PatternShapes), which
#      unify dielectrics, ground planes, and wires into one geometric model
#      with a common (order, height, width, thickness, x, y, z) representation.
#   3. Walk PatternShapes, find intersections between conductors and
#      dielectric layers, and emit FasterCap panel files (bottom/side/top
#      faces) plus the corresponding D (dielectric) / C (conductor) records
#      in the main FasterCap .lst pattern file.
#
# NOTE: the low-level panel/record writer functions (write_dielectric_*,
# write_wire_*, insert_dielectric_into_pattern_file*,
# insert_conductor_into_pattern_file*) have been moved to
# fastercap_panel_io.py so C25D2FasterCap.py can reuse them without
# duplicating panel-format logic. They're called here as panel_io.<name>(...)
# with currentpath passed explicitly as the first argument.


# Structures used while parsing processfile (3D Patterns)# 
class Dielectrics:
  # Represents one dielectric layer as declared in a process tech file (3D).
  name = ""
  thickness = 0.0
  epsilon = 0.0

  def __init__(self, name: str, thickness: float, epsilon: float) -> None:
    self.name = name
    self.thickness = thickness
    self.epsilon = epsilon
  
  def print_contents(self) -> None:
    print("Name: " + self.name + " Thickness: " + self.thickness + " Epsilon: " + self.epsilon)

# Structures used while parsing processfile (2D Patterns)# 
class Dielectrics_2D:
  # 2D counterpart of Dielectrics: a dielectric layer described by height
  # (rather than 3D thickness) and epsilon.
  name = ""
  thickness = 0.0
  epsilon = 0.0

  def __init__(self, name: str, height: float, epsilon: float) -> None:
    self.name = name
    self.height = height
    self.epsilon = epsilon
  
  def print_contents(self) -> None:
    print("Name: " + self.name + " Height: " + self.height + " Epsilon: " + self.epsilon)



# Structures used while parsing UniversalFormat #
class UniversalFormatDielectrics:
  # stored while parsing DIELECTRIC line #
  # Holds one DIELECTRIC record parsed from a 3D universal-format "wires" file.
  # z is the lower bound (in the height/length axis) of the slab, thickness
  # is its extent.
  name = ""
  thickness = 0.0
  z = 0.0
  epsilon = 0.0

  def __init__(self, name: str, z: float, thickness: float, epsilon: float):
    self.name = name
    self.z = z
    self.thickness = thickness
    self.epsilon = epsilon

  def set_coordinates(self, x, y, width, length):
    self.x = x
    self.y = y
    self.width = width
    self.length = length

class UniversalFormatDielectrics_2D:
  # stored while parsing DIELECTRIC line #
  # 2D counterpart of UniversalFormatDielectrics: uses y instead of z,
  # and height instead of thickness.
  name = ""
  height = 0.0
  z = 0.0
  epsilon = 0.0

  def __init__(self, name: str, y: float, height: float, epsilon: float):
    self.name = name
    self.y = y
    self.height = height
    self.epsilon = epsilon

  def set_coordinates(self, x, y, width, length):
    self.x = x
    self.y = y
    self.width = width
    self.length = length

class UniversalFormatGroundPlanes:
  # stored while parsing GROUND_PLANE line #
  # metallevel indicates which metal layer number the ground plane belongs to.
  name = ""
  thickness = 0.0
  z = 0.0
  metallevel = 0

  def __init__(self, name: str, z: float, thickness: float, metallevel: int):
    self.name = name
    self.z = z
    self.thickness = thickness
    self.metallevel = metallevel

  def set_coordinates(self, x, y, width, length):
    self.x = x
    self.y = y
    self.width = width
    self.length = length

class UniversalFormatGroundPlanes_2D:
  # stored while parsing GROUND_PLANE line #
  # 2D counterpart of UniversalFormatGroundPlanes.
  name = ""
  thickness = 0.0
  y = 0.0
  metallevel = 0

  def __init__(self, name: str, y: float, thickness: float, metallevel: int):
    self.name = name
    self.y = y
    self.thickness = thickness
    self.metallevel = metallevel

  def set_coordinates(self, x, y, width, length):
    self.x = x
    self.y = y
    self.width = width
    self.length = length

class UniversalFormatWires:
  # Holds one WIRE record parsed from a 3D universal-format file: position,
  # cross-section (width x thickness), extruded length, and voltage.
  name = ""
  num = 0 
  x = 0.0
  y = 0.0
  z = 0.0
  width = 0.0
  thickness = 0.0
  length = 0.0
  voltage = 0
  groundplane = False

  def __init__(self, name: str, num: int, x: float, y: float, z: float, 
              width: float, thickness: float, length: float, voltage: int):
    self.name = name
    self.num = num
    self.x = x
    self.y = y
    self.z = z
    self.width = width
    self.thickness = thickness
    self.length = length
    self.voltage = voltage

class UniversalFormatWires_2D:
  # 2D counterpart of UniversalFormatWires: no z/length axis, just an (x, y)
  # position with width and height.
  name = ""
  num = 0 
  x = 0.0
  y = 0.0
  # z = 0.0
  width = 0.0
  height = 0.0
  # length = 0.0
  voltage = 0
  groundplane = False

  def __init__(self, name: str, num: int, x: float, y: float, 
              width: float, height: float, voltage: int):
    self.name = name
    self.num = num
    self.x = x
    self.y = y
    self.width = width
    self.height = height
    self.voltage = voltage

# Structures used after parsing UniversalFormat #
class Shapes:
  # Unified 3D geometric representation used after parsing: both dielectrics
  # and conductors (wires/ground planes) become Shapes so the rest of the
  # pipeline (intersection detection, panel writing) can treat them uniformly.
  # shapetype: 0 = Dielectric, 1 = Metal/conductor.
  # (shapex, shapey, shapez) is the lower-left-ish reference corner; note
  # shapey <-> z-axis and shapez <-> y-axis, per the "LL corner y <-> z" swap
  # used throughout TranslateUniversalFile.
  
  name = ""
  shapeorder = 0
  shapeheight = 0
  shapewidth = 0
  shapethickness = 0
  shapetype = 0
  shapex = 0.0
  shapey = 0.0
  shapez = 0.0

  def __init__(self, name: str, order: float, height: float, thickness: float, width: float, xcoordinate: float, ycoordinate: float, zcoordinate: float, shapetype: int) -> None:
    self.name = name
    self.shapeorder = order
    self.shapeheight = height
    self.shapewidth = width
    self.shapethickness = thickness
    self.shapex = xcoordinate
    self.shapey = ycoordinate
    self.shapez = zcoordinate
    self.shapetype = shapetype
  
  def print_contents(self) -> None:
    print("Name: " + self.name + " order: " + str(self.shapeorder) + " height: " + str(self.shapeheight) + " width: " + str(self.shapewidth) + " thickness: " + str(self.shapethickness) + " xcoord: " + str(self.shapex) + " ycoord: " + str(self.shapey) + " type: " + str(self.shapetype))

class Shapes_2D:
  # 2D counterpart of Shapes. Adds groundplanes/contactwithplane flags used
  # by the 2D dielectric-panel-writing logic to avoid emitting duplicate
  # overlapping panels where a dielectric touches a ground plane.
  
  name = ""
  shapeorder = 0
  shapeheight = 0
  shapewidth = 0
  # shapethickness = 0
  shapetype = 0
  shapex = 0.0
  shapey = 0.0
  # shapez = 0.0
  groundplanes = 0
  contactwithplane = 0

  def __init__(self, name: str, order: float, height: float, width: float, xcoordinate: float, ycoordinate: float, shapetype: int, groundplane: int, contactwithplane: int) -> None:
    self.name = name
    self.shapeorder = order
    self.shapeheight = height
    self.shapewidth = width
    # self.shapethickness = thickness
    self.shapex = xcoordinate
    self.shapey = ycoordinate
    # self.shapez = zcoordinate
    self.shapetype = shapetype
    self.groundplane = groundplane
    self.contactwithplane = contactwithplane
  
  def print_contents(self) -> None:
    print("Name: " + self.name + " order: " + str(self.shapeorder) + " height: " + str(self.shapeheight) + " width: " + str(self.shapewidth)  + " xcoord: " + str(self.shapex) + " ycoord: " + str(self.shapey) + " type: " + str(self.shapetype) + " ground plane: " + str(self.groundplane) + " in contact with ground plane " + str(self.contactwithplane))

def TranslateUniversalFile(Universalfilename: str, FasterCapfilename: str, mode: int):
  # Top-level driver: walks the universal-format folder tree, and for every
  # file named "wires" (one per pattern), parses it and emits the
  # corresponding FasterCap .lst file (via extractFasterCapfile /
  # extractFasterCapfile_2D depending on mode).
  #
  # mode: 1 = 3D geometry, 2 = 2D geometry.
  #
  # The two mode branches below are structurally parallel: parse
  # PATTERN / GROUND_PLANE / DIELECTRIC / WIRE / WINDOW_BBOX / SIM_WIN_EXT
  # records line-by-line into temp lists, apply window extension, then map
  # everything into PatternShapes (the unified Shapes / Shapes_2D list) before
  # calling the file-writing routine.

  print(f"DEBUG: TranslateUniversalFile: {Universalfilename} to {FasterCapfilename}, mode {mode}")
  global patternswindowwidth
  global patternswindowthickness
  global patternswindowheight
  global window_min_x
  global window_min_z
  global window_min_y
  global window_max_x
  global window_max_z
  global window_max_y
  global base_epsilon

  # check if specified directory paths end with '/' #
  # otherwise append '/' at the end                 #
  if not FasterCapfilename.endswith("/"):
    tempfastercapfilename = FasterCapfilename + "/"
  else:
    tempfastercapfilename = FasterCapfilename

  if not Universalfilename.endswith("/"):
    tempuniversalfilename = Universalfilename + "/"
  else:
    tempuniversalfilename = Universalfilename

  # Panel geometry files (Dielectrics/, Wires/) are shared across every
  # pattern converted in this run, written once directly under the
  # top-level output folder (fastercap_output_folder/Dielectrics,
  # fastercap_output_folder/Wires) rather than duplicated per-pattern.
  global currentpath
  currentpath = os.path.normpath(tempfastercapfilename)

  # walk each directory tree for specified Universalfilename #
  for root, dirs, files in os.walk(tempuniversalfilename):

    for directory in dirs: # found directory #

      # create directory in Fastercap directory if it doesn't exist #
      relative_dir = os.path.relpath(root, tempuniversalfilename)
      fastercap_root = os.path.normpath(os.path.join(tempfastercapfilename, relative_dir))
      dirpath = os.path.join(fastercap_root, directory)
      if not os.path.exists(dirpath):
        os.makedirs(dirpath)
      
    for file in files: # found file #
      if (file == "wires"): # check if file is wires #
        tempwires = []
        tempdielectrics = []
        tempgroundplanes = []
        # get the fastercap pattern file root #
        relative_dir = os.path.relpath(root, tempuniversalfilename)
        fastercap_root = os.path.normpath(os.path.join(tempfastercapfilename, relative_dir))
        # get fastercap pattern file name #
        TempFasterCapfilename = os.path.join(fastercap_root, file) + '.lst'
        # if fastercap pattern root doesn't exist create it #
        if not os.path.exists(fastercap_root):
          os.makedirs(fastercap_root)

        fname = os.path.join(root, file)
        print(f"Translating Universal Pattern {fname} to FasterCap pattern {TempFasterCapfilename}")

        # TOOD: check for errors in files #
        errorcode = 0
        
        # base epsilon is the value of the first in order dielectric #
        # 4.1 is the default value of p1_1 #
        # first dielectric is used to check if we are parsing the first dielectric instance #
        base_epsilon = 4.1 
        length = 0
        first_dielectric = True
        
        f = open(fname)

        #  3D MODE #
        if (mode == 1):

          dielorder = 0
          lineindex = 0
          groundplane_num = 0
          lower_z = 0 # M0_w0
          upper_z = 100
          for line in f:
            linesplit = [x for x in line.split(" ") if x != ''] # split lines on space and filter out empty tokens #
            # check first token #
            if linesplit[0] == "PATTERN":
              patternname = linesplit[1]

            # NOTE: we have 1 or 2 Ground Planes               #
            # Low Ground Plane Gives us lower height and       #
            # High Ground Plane sets the upper height bound    #
            # DIELECTIS and Wires are normalized based on that #
            elif linesplit[0] == "GROUND_PLANE":
              z = float(linesplit[4])
              thickness = float(linesplit[7])
              if thickness == float(0.0):
                # zero-thickness ground plane gets a tiny nominal thickness so
                # it still forms a valid panel geometry
                z += -0.1
                thickness = 0.1
              groundplane_num += 1
              if groundplane_num == 1: # lower ground #
                lower_z = float(linesplit[5])
              elif groundplane_num == 2: # upper ground #
                upper_z = z
              if normalized_heights == True:
                z -= lower_z
              tempgroundplanes.append(UniversalFormatGroundPlanes(linesplit[2], z, thickness, int(linesplit[1])))

            elif linesplit[0] == "DIELECTRIC":
              if first_dielectric == True:
                base_epsilon = float(linesplit[6])
                first_dielectric = False
              
              # check if the heights are normalized                             #
              # if true then check if current height is between lower and upper #
              # if true then keep dielectric/metal                              #      
              # else continue to next dielectric/metal                          #
              z = float(linesplit[3])
              height_plus_z = float(linesplit[4])
              if normalized_heights == True:
                if (z < lower_z) or (height_plus_z > upper_z):
                  continue
                else:
                  z -= lower_z 
                
              tempdielectrics.append(UniversalFormatDielectrics(linesplit[1], z,
                                                                float(linesplit[4]) - float(linesplit[3]),
                                                                float(linesplit[6])))
            elif linesplit[0] == "WIRE":
              name = linesplit[2]
              num = int(linesplit[1])
              x = float(linesplit[4])
              y = 0.0
              
              # check if the heights are normalized                             #
              # if true then check if current height is between lower and upper #
              # if true then keep dielectric/metal                              #      
              # else continue to next dielectric/metal                          #
              z = float(linesplit[5])
              height_plus_z = float(linesplit[11])
              if normalized_heights == True:
                if (z < lower_z) or (height_plus_z > upper_z):
                  continue
                else:
                  z -= lower_z
                  
              width = float(linesplit[7]) - float(linesplit[4])
              thickness = float(linesplit[11]) - float(linesplit[5])
              length = float(linesplit[16])
              voltage = int(linesplit[18])
              tempwires.append(UniversalFormatWires(name, num, x, y, z, width, thickness, length, voltage))
            elif linesplit[0] == "WINDOW_BBOX":
              length = float(linesplit[8])
              window_min_x = float(linesplit[2])
              window_min_y = 0
              window_min_z = float(linesplit[3])
              window_max_x = float(linesplit[5])
              window_max_z = float(linesplit[6])
              window_max_y = length
            elif linesplit[0] == "SIM_WIN_EXT" and user_window_ext == False:
              # extend BBOX on x z and y axis #
              # (only applied here if the user did NOT supply their own
              # override via CLI args — see user_window_ext handling below)
              window_min_x += float(linesplit[2])
              window_min_z += float(linesplit[3])
              window_max_x += float(linesplit[5])
              window_max_z += float(linesplit[6])
              window_min_y += float(linesplit[8]) 
              window_max_y += float(linesplit[9]) 
            else: # unkown first token #
              continue

          # add user window extension if provided #
          if user_window_ext == True:
            # extend BBOX on x z and y axis #
            window_min_x += window_min_x_ext
            window_min_z += window_min_z_ext
            window_max_x += window_max_x_ext
            window_max_z += window_max_z_ext
            window_min_y += window_min_y_ext 
            window_max_y += window_max_y_ext 

          patternswindowwidth = window_max_x - window_min_x
          patternswindowthickness = window_max_z - window_min_z
          patternswindowheight = window_max_y - window_min_y

          # map Universal Format Data Structures to Shapes #
          # NOTE: height == length (y-axis) #
          dielorder = 0
          for dielectric in tempdielectrics:
            # Each dielectric slab spans the full window (width x height),
            # positioned in the "thickness" axis (shapey) at its parsed z.
            shapetype = 0 # Dielectric
            shapeorder = dielorder
            dielorder += 1
            shapename = dielectric.name
            shapeheight = round(patternswindowheight , 6)
            shapethickness = round(dielectric.thickness, 6)
            shapewidth = round(patternswindowwidth, 6)
            # NOTE: LL corner y <-> z #
            LLcornerx = window_min_x
            LLcornery = dielectric.z
            LLcornerz = window_min_y
            processDielectrics.append(Dielectrics(shapename, shapethickness, dielectric.epsilon))
            PatternShapes.append(Shapes(shapename, shapeorder, shapeheight, shapethickness, shapewidth, LLcornerx, LLcornery, LLcornerz, shapetype))
            # kept on the shape, as processDielectrics grows across patterns #
            PatternShapes[-1].epsilon = dielectric.epsilon

          for groundplane in tempgroundplanes:
            # Ground planes also span the full window width, at their own
            # thickness/z position. shapeorder is derived from the metal
            # layer number embedded in the name (e.g. "M2_..." -> order 2).
            shapetype = 1 # Metal
            shapename = groundplane.name
            shapeorder = shapename.split("_")[0].split("M")[1]
            shapeheight = round(patternswindowheight , 6)
            shapethickness = round(groundplane.thickness, 6)
            shapewidth = round(patternswindowwidth, 6)
            # NOTE: LL corner y <-> z #
            LLcornerx = window_min_x
            LLcornery = groundplane.z
            LLcornerz = window_min_y
            PatternShapes.append(Shapes(shapename, shapeorder, shapeheight, shapethickness, shapewidth, LLcornerx, LLcornery, LLcornerz, shapetype))
          
          # NOTE: Wires y & length should be preserved, not extented #
          for wire in tempwires:
            # Wires keep their own individual position/geometry (unlike
            # dielectrics/ground planes which span the full window).
            shapetype = 1 # Metal
            shapename = wire.name
            shapeorder = shapename.split("_")[0].split("M")[1]
            shapeheight = round(wire.length, 6)
            shapethickness = round(wire.thickness, 6)
            shapewidth = round(wire.width, 6)
            # NOTE: LL corner y <-> z #
            LLcornerx = wire.x
            LLcornery = wire.z
            LLcornerz = wire.y
            PatternShapes.append(Shapes(shapename, shapeorder, shapeheight, shapethickness, shapewidth, LLcornerx, LLcornery, LLcornerz, shapetype))

          # for i in range(len(PatternShapes)):  
          #   PatternShapes[i].print_contents()

          # print(base_epsilon)

          # extractFasterCapfile() is the previous row-scan writer #
          extractFasterCapfile_layered(TempFasterCapfilename)
          # clear data global data structure #
          PatternShapes.clear()
        elif (mode == 2): # 2D MODE #
          print("INFO:2D Mode Enabled")
          dielorder = 0
          lineindex = 0
          groundplane_num = 0
          lower_y = 0 # M0_w0
          upper_y = 100
          for line in f:
            linesplit = [x for x in line.split(" ") if x != ''] # split lines on space and filter out empty tokens #
            
            # check first token #
            if linesplit[0] == "PATTERN":
              patternname = linesplit[1]

            # NOTE: we have 1 or 2 Ground Planes               #
            # Low Ground Plane Gives us lower height and       #
            # High Ground Plane sets the upper height bound    #
            # DIELECTIS and Wires are normalized based on that #
            elif linesplit[0] == "GROUND_PLANE":
              y = float(linesplit[4])
              thickness = float(linesplit[7])
              if thickness == float(0.0):
                y += -0.1
                thickness = 0.1
              groundplane_num += 1
              total_ground_planes = groundplane_num
              if groundplane_num == 1: # lower ground #
                lower_y = float(linesplit[5])
              elif groundplane_num == 2: # upper ground #
                upper_y = y
              if normalized_heights == True:
                y -= lower_y
              
              # print(f"DEBUG-GROUND-PLANES: Ground Plane {linesplit[2]} => y = {y}, upper_y = {upper_y}, lower_y = {lower_y}")
              tempgroundplanes.append(UniversalFormatGroundPlanes_2D(linesplit[2], y, thickness, int(linesplit[1])))

            elif linesplit[0] == "DIELECTRIC":
              if first_dielectric == True:
                base_epsilon = float(linesplit[6])
                first_dielectric = False
              
              # check if the heights are normalized                             #
              # if true then check if current height is between lower and upper #
              # if true then keep dielectric/metal                              #      
              # else continue to next dielectric/metal                          #
              y = float(linesplit[3])
              height_plus_y = float(linesplit[4])
              if normalized_heights == True:
                if (y < lower_y) or (height_plus_y > upper_y):
                  # print(f"DEBUG-2D: Skipping Dielectric {linesplit[1]}")
                  # print(f"\ty < lower_y => {y} < {lower_y}")
                  # print(f"\theight_plus_y > upper_y => {height_plus_y} > {upper_y}")
                  continue
                else:
                  y -= lower_y 
                  # # print(f"DEBUG-2D: Setting for Dielectric {linesplit[1]} y = {y} (- {lower_y})")
                
              # print(f"DEBUG-DIELECTRICS: Dielectric {linesplit[1]} parsed with y = {y}, height plus y = {height_plus_y} and thickness {thickness}")
              tempdielectrics.append(UniversalFormatDielectrics_2D(linesplit[1], y,
                                                                round(float(linesplit[4]) - float(linesplit[3]),4),
                                                                float(linesplit[6])))
              
            elif linesplit[0] == "WIRE":
              name = linesplit[2]
              num = int(linesplit[1])
              x = float(linesplit[4])
              # y = 0.0
              
              # check if the heights are normalized                             #
              # if true then check if current height is between lower and upper #
              # if true then keep dielectric/metal                              #      
              # else continue to next dielectric/metal                          #
              y = float(linesplit[5])
              height_plus_y = float(linesplit[11])
              if normalized_heights == True:
                if (y < lower_y) or (height_plus_y > upper_y):
                  continue
                else:
                  y -= lower_y
                  
              width = float(linesplit[7]) - float(linesplit[4])
              height = float(linesplit[11]) - float(linesplit[5])
              # length = float(linesplit[16])
              voltage = int(linesplit[16])

              # print(f"DEBUG-CONDUCTORS: Conductor {linesplit[2]} => num = {num}, x = {x}, y = {y}, width = {width}, height = {height}")

              tempwires.append(UniversalFormatWires_2D(name, num, x, y, width, height, voltage))
              # print(f"DEBUG-2D: ** Inserted Wire {linesplit[1]} ({num}) with x = {x}, y = {y}, width = {width}, height = {height} and voltage {voltage}")

            elif linesplit[0] == "WINDOW_BBOX":
              # length = float(linesplit[8])
              window_min_x = float(linesplit[2])
              # window_min_ = 0
              window_min_y = float(linesplit[3])
              window_max_x = float(linesplit[5])
              window_max_y = float(linesplit[6])
              # window_max_y = length
            elif linesplit[0] == "SIM_WIN_EXT" and user_window_ext == False:
              # extend BBOX on x z and y axis #
              window_min_x += float(linesplit[2])
              window_min_y += float(linesplit[3])
              window_max_x += float(linesplit[5])
              window_max_y += float(linesplit[6])
              # window_min_y += float(linesplit[8]) 
              # window_max_y += float(linesplit[9]) 
            else: # unkown first token #
              continue

          # add user window extension if provided #
          if user_window_ext == True:
            # extend BBOX on x z and y axis #
            window_min_x += window_min_x_ext
            # window_min_z += window_min_z_ext
            window_max_x += window_max_x_ext
            # window_max_z += window_max_z_ext
            window_min_y += window_min_y_ext 
            window_max_y += window_max_y_ext 

          patternswindowwidth = window_max_x - window_min_x
          # patternswindowthickness = window_max_z - window_min_z
          patternswindowheight = window_max_y - window_min_y

          # print(f"DEBUG-2D: Pattern Window data:")
          # print(f"\t\tpatternswindowwidth = {patternswindowwidth}\n\t\tpatternswindowheight = {patternswindowheight}")

          # map Universal Format Data Structures to Shapes #
          # NOTE: height == length (y-axis) #
          # NOTE: this block re-checks `mode` even though we're already
          # inside the `elif (mode == 2):` branch — the mode==1 sub-branch
          # below is therefore dead code in practice, kept as-is here.
          dielorder = 0
          if (mode == 1):
            for dielectric in tempdielectrics:
              shapetype = 0 # Dielectric
              shapeorder = dielorder
              dielorder += 1
              shapename = dielectric.name
              shapeheight = round(patternswindowheight , 6)
              shapethickness = round(dielectric.thickness, 6)
              shapewidth = round(patternswindowwidth, 6)
              # NOTE: LL corner y <-> z #
              LLcornerx = window_min_x
              LLcornery = dielectric.z
              LLcornerz = window_min_y
              processDielectrics.append(Dielectrics(shapename, shapethickness, dielectric.epsilon))
              PatternShapes.append(Shapes(shapename, shapeorder, shapeheight, shapethickness, shapewidth, LLcornerx, LLcornery, LLcornerz, shapetype))

            for groundplane in tempgroundplanes:
              shapetype = 1 # Metal
              shapename = groundplane.name
              shapeorder = shapename.split("_")[0].split("M")[1]
              shapeheight = round(patternswindowheight , 6)
              shapethickness = round(groundplane.thickness, 6)
              shapewidth = round(patternswindowwidth, 6)
              # NOTE: LL corner y <-> z #
              LLcornerx = window_min_x
              LLcornery = groundplane.z
              LLcornerz = window_min_y
              PatternShapes.append(Shapes(shapename, shapeorder, shapeheight, shapethickness, shapewidth, LLcornerx, LLcornery, LLcornerz, shapetype))
            
            # NOTE: Wires y & length should be preserved, not extented #
            for wire in tempwires:
              shapetype = 1 # Metal
              shapename = wire.name
              shapeorder = shapename.split("_")[0].split("M")[1]
              shapeheight = round(wire.length, 6)
              shapethickness = round(wire.thickness, 6)
              shapewidth = round(wire.width, 6)
              # NOTE: LL corner y <-> z #
              LLcornerx = wire.x
              LLcornery = wire.z
              LLcornerz = wire.y
              PatternShapes.append(Shapes(shapename, shapeorder, shapeheight, shapethickness, shapewidth, LLcornerx, LLcornery, LLcornerz, shapetype))
          elif (mode == 2):
            for dielectric in tempdielectrics:
              # Dielectrics span the full window width; shapey is the
              # dielectric's own y position (not offset by window_min_y,
              # unlike the 3D branch).
              shapetype = 0 # Dielectric
              shapeorder = dielorder
              dielorder += 1
              shapename = dielectric.name
              shapeheight = round(dielectric.height , 6)
              # shapethickness = round(dielectric.thickness, 6)
              shapewidth = round(patternswindowwidth, 6)
              # NOTE: LL corner y <-> z #
              LLcornerx = window_min_x
              LLcornery = dielectric.y 
              # LLcornerz = dielectric.z
              # print(f"\tDEBUG-2D: Inserting to pattern shapes the dielectric {shapename} with LL {LLcornerx} {LLcornery}, shape height = {shapeheight}, shape width = {shapewidth}, shape order = {shapeorder}")
              processDielectrics.append(Dielectrics_2D(shapename, shapeheight, dielectric.epsilon))
              PatternShapes.append(Shapes_2D(shapename, shapeorder, shapeheight, shapewidth, LLcornerx, LLcornery, shapetype, 0, 0))

            for groundplane in tempgroundplanes:
              shapetype = 1 # Metal
              shapename = groundplane.name
              shapeorder = shapename.split("_")[0].split("M")[1]
              shapeheight = round(groundplane.thickness , 6)
              # shapethickness = round(groundplane.thickness, 6)
              shapewidth = round(patternswindowwidth, 6)
              # NOTE: LL corner y <-> z #
              LLcornerx = window_min_x
              LLcornery = groundplane.y
              # LLcornerz = window_min_y
              # print(f"DEBUG-2D: Inserting to pattern shapes the ground plane {shapename} with LL {LLcornerx} {LLcornery}, shape height = {shapeheight}, shape width = {shapewidth}")

              # groundplane flag (7th positional arg) is set to 1 here
              PatternShapes.append(Shapes_2D(shapename, shapeorder, shapeheight, shapewidth, LLcornerx, LLcornery, shapetype, 1, 0))
            
            # NOTE: Wires y & length should be preserved, not extented #
            for wire in tempwires:
              shapetype = 1 # Metal
              shapename = wire.name
              shapeorder = shapename.split("_")[0].split("M")[1]
              shapeheight = round(wire.height, 6)
              # shapethickness = round(wire.thickness, 6)
              shapewidth = round(wire.width, 6)
              # NOTE: LL corner y <-> z #
              LLcornerx = wire.x
              LLcornery = wire.y
              # LLcornerz = wire.y
              PatternShapes.append(Shapes_2D(shapename, shapeorder, shapeheight, shapewidth, LLcornerx, LLcornery, shapetype, 0, 0))
            
            # print("INFO-2D: Shapes")
            # print("---------------------------------------")
            # for i in range(len(PatternShapes)):  
            #   PatternShapes[i].print_contents()
            # print("---------------------------------------")
            

          # print(base_epsilon)

          extractFasterCapfile_2D(TempFasterCapfilename)
          # clear data global data structure #
          PatternShapes.clear()

def process_intersection():
  # Unused placeholder.
  pass

def write_ground_planes_2D(minimumconductorlayer, maximumconductorlayer, conductorsintersections, conductorindexlist, dielindexlist, FasterCapFile, write, ground):
  # Write panel entries specifically for 2D conductors flagged as ground
  # planes (Shapes_2D.groundplane == 1) that have no dielectric intersections.
  # Structurally similar to write_conductors_2D's "no intersections" branch,
  # but filtered to ground-plane shapes only.

  conductorindex = 0 
  for intersectionslist in conductorsintersections:

    conductororder = int(PatternShapes[conductorindexlist[conductorindex]].name.split("_")[0].split("M")[1])
    
    if (conductororder < minimumconductorlayer):
      minimumconductorlayer = conductororder
    
    if (conductororder > maximumconductorlayer):
      maximumconductorlayer = conductororder

    if (PatternShapes[conductorindexlist[conductorindex]].groundplane == 1):
    #   if ((write == 1) and (ground == 1)):
    #     groundconductorexists = 1

    #     continue  
    # if (len(intersectionslist) == 0):
      # print(f"DEBUG-2D: For conductor {PatternShapes[conductorindexlist[conductorindex]].name} => no intersections, ground plane = {PatternShapes[conductorindexlist[conductorindex]].groundplane}")
      groundconductorexists = 1
      if ((write == 1) and (ground == 1)):
        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-bottom.txt"
        FasterCapFile.write("* {}\n".format(PatternShapes[conductorindexlist[conductorindex]].name))          
        FasterCapFile.write("*\n")          
        
        panel_io.write_wire_bottom_panel_2D(currentpath, conductorfile, 
                                PatternShapes[conductorindexlist[conductorindex]].name, 
                                PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                                PatternShapes[conductorindexlist[conductorindex]].shapeheight
                                )
        panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                          conductorfile,
                                          float(1.0e-6),
                                          PatternShapes[conductorindexlist[conductorindex]].shapex,
                                          PatternShapes[conductorindexlist[conductorindex]].shapey,
                                          )
        FasterCapFile.write(" + \n")

        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-sides.txt"
        panel_io.write_wire_side_panels_2D(currentpath, conductorfile, 
                              PatternShapes[conductorindexlist[conductorindex]].name, 
                              PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                              PatternShapes[conductorindexlist[conductorindex]].shapeheight
                              )
        panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                            conductorfile,
                                            float(1.0e-6),
                                            PatternShapes[conductorindexlist[conductorindex]].shapex,
                                            PatternShapes[conductorindexlist[conductorindex]].shapey
                                            )
        FasterCapFile.write(" + \n")

        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-top.txt"
        panel_io.write_wire_top_panel_2D(currentpath, conductorfile, 
                            PatternShapes[conductorindexlist[conductorindex]].name, 
                            PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                            PatternShapes[conductorindexlist[conductorindex]].shapeheight
                            )
        panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                          conductorfile,
                                          round(base_epsilon * float(1e-6), 8),
                                          PatternShapes[conductorindexlist[conductorindex]].shapex,
                                          PatternShapes[conductorindexlist[conductorindex]].shapey,
                                          )
        FasterCapFile.write("\n\n")
    conductorindex += 1

def write_conductors_2D(minimumconductorlayer, maximumconductorlayer, conductorsintersections, conductorindexlist, dielindexlist, FasterCapFile, write, ground):
  # Write panel entries (bottom/side/top) for 2D conductors.
  #
  # This function serves double duty depending on `write` and `ground`:
  #   - write=0            : dry-run pass, only used to compute
  #                           minimum/maximum conductor layer bounds
  #                           (called once before any writing happens)
  #   - write=1, ground=0  : write ordinary (non-ground-plane) conductors
  #   - write=1, ground=1  : skip ground-plane conductors entirely (they're
  #                           handled separately by write_ground_planes_2D)
  #
  # For each conductor:
  #   - If it has no dielectric intersections, write bottom/side/top panels
  #     directly against a fixed default permittivity (1e-6 outer,
  #     base_epsilon inner).
  #   - If it does intersect one or more dielectrics, write one "sides" +
  #     "top" panel set per intersecting dielectric layer, and one "bottom"
  #     panel using the first intersection's permittivity, so that each
  #     dielectric-conductor contact boundary gets electrically correct
  #     permittivity values on either side.

  conductorindex = 0 
  for intersectionslist in conductorsintersections:

    conductororder = int(PatternShapes[conductorindexlist[conductorindex]].name.split("_")[0].split("M")[1])
    
    if (conductororder < minimumconductorlayer):
      minimumconductorlayer = conductororder
    
    if (conductororder > maximumconductorlayer):
      maximumconductorlayer = conductororder

    if (PatternShapes[conductorindexlist[conductorindex]].groundplane == 1):
      if ((write == 1) and (ground == 1)):
        groundconductorexists = 1
        continue  

    if (len(intersectionslist) == 0):
      # print(f"DEBUG-2D: Writting conductor {PatternShapes[conductorindexlist[conductorindex]].name} => no intersections, ground plane = {PatternShapes[conductorindexlist[conductorindex]].groundplane}")
      groundconductorexists = 1
      if ((write == 1) and (ground == 1)):
        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-bottom.txt"
        FasterCapFile.write("* {}\n".format(PatternShapes[conductorindexlist[conductorindex]].name))          
        FasterCapFile.write("*\n")          
        
        panel_io.write_wire_bottom_panel_2D(currentpath, conductorfile, 
                                PatternShapes[conductorindexlist[conductorindex]].name, 
                                PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                                PatternShapes[conductorindexlist[conductorindex]].shapeheight
                                )
        panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                          conductorfile,
                                          float(1.0e-6),
                                          PatternShapes[conductorindexlist[conductorindex]].shapex,
                                          PatternShapes[conductorindexlist[conductorindex]].shapey,
                                          )
        FasterCapFile.write(" + \n")

        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-sides.txt"
        panel_io.write_wire_side_panels_2D(currentpath, conductorfile, 
                              PatternShapes[conductorindexlist[conductorindex]].name, 
                              PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                              PatternShapes[conductorindexlist[conductorindex]].shapeheight
                              )
        panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                            conductorfile,
                                            float(1.0e-6),
                                            PatternShapes[conductorindexlist[conductorindex]].shapex,
                                            PatternShapes[conductorindexlist[conductorindex]].shapey
                                            )
        FasterCapFile.write(" + \n")

        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-top.txt"
        panel_io.write_wire_top_panel_2D(currentpath, conductorfile, 
                            PatternShapes[conductorindexlist[conductorindex]].name, 
                            PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                            PatternShapes[conductorindexlist[conductorindex]].shapeheight
                            )
        panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                          conductorfile,
                                          round(base_epsilon * float(1e-6), 8),
                                          PatternShapes[conductorindexlist[conductorindex]].shapex,
                                          PatternShapes[conductorindexlist[conductorindex]].shapey,
                                          )
        FasterCapFile.write("\n\n")

    else:

      intersectiondiel = 0
      
      for intersection in intersectionslist:
        # print(f"DEBUG-2D: Intersection = {intersection}")

        if (intersectiondiel == 0):
          # first intersecting dielectric -> also write the bottom panel
          if ((write == 1) and (ground == 0)):

            if (PatternShapes[conductorindexlist[conductorindex]].groundplane == 1):
              continue
            # print(f"DEBUG-2D (1): Writing conductor {PatternShapes[conductorindexlist[conductorindex]].name} => intersections, ground plane = {PatternShapes[conductorindexlist[conductorindex]].groundplane}")
            
            FasterCapFile.write("* {}\n".format(PatternShapes[conductorindexlist[conductorindex]].name))          
            FasterCapFile.write("*\n")          
          
            conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[intersection].shapeheight) + "-bottom.txt"
            panel_io.write_wire_bottom_panel_2D(currentpath, conductorfile, 
                                    PatternShapes[conductorindexlist[conductorindex]].name, 
                                    PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                                    PatternShapes[conductorindexlist[conductorindex]].shapeheight
                                    )
            panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                              conductorfile,
                                              round(float(processDielectrics[PatternShapes[dielindexlist[intersection]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              PatternShapes[conductorindexlist[conductorindex]].shapex,
                                              PatternShapes[intersection].shapey,
                                              )
            FasterCapFile.write(" + \n")

        if ((write == 1) and (ground == 0)):
          # every intersecting dielectric -> write a side panel using that
          # dielectric's own epsilon
          # print(f"DEBUG-2D (2): Writing conductor {PatternShapes[conductorindexlist[conductorindex]].name} => intersections, ground plane = {PatternShapes[conductorindexlist[conductorindex]].groundplane}")

          conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[intersection].shapeheight) + "-sides.txt"
          panel_io.write_wire_side_panels_2D(currentpath, conductorfile, 
                                PatternShapes[conductorindexlist[conductorindex]].name, 
                                PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                                PatternShapes[intersection].shapeheight
                                )
          panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                              conductorfile,
                                              round(float(processDielectrics[PatternShapes[dielindexlist[intersection]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              PatternShapes[conductorindexlist[conductorindex]].shapex,
                                              PatternShapes[intersection].shapey,
                                              )
          FasterCapFile.write(" + \n")

        if (intersectiondiel == len(intersectionslist) - 1):
          # last intersecting dielectric -> also write the top panel, using
          # the *next* dielectric layer's epsilon (shapeorder + 1)
          if ((write == 1) and (ground == 0)):
            # print(f"DEBUG-2D (3): Writing conductor {PatternShapes[conductorindexlist[conductorindex]].name} => intersections, ground plane = {PatternShapes[conductorindexlist[conductorindex]].groundplane}")

            conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[intersection].shapeheight) + "-top.txt"
            panel_io.write_wire_top_panel_2D(currentpath, conductorfile, 
                                PatternShapes[conductorindexlist[conductorindex]].name, 
                                PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                                PatternShapes[intersection].shapeheight
                                )
            panel_io.insert_conductor_into_pattern_file_2D(currentpath, FasterCapFile, 
                                              conductorfile,
                                              round(float(processDielectrics[PatternShapes[dielindexlist[intersection]].shapeorder + 1].epsilon) * float(1.0e-6), 8),
                                              PatternShapes[conductorindexlist[conductorindex]].shapex,
                                              PatternShapes[intersection].shapey,
                                              )
            FasterCapFile.write("\n\n")

        intersectiondiel += 1
    conductorindex += 1
  return groundconductorexists, minimumconductorlayer, maximumconductorlayer

def write_dielectrics_2D(first_dielectric, dielintersections, dielindexlist, minimumconductorlayer, maximumconductorlayer, groundconductorexists, FasterCapFile, write_no_intersections):
  # Write panel entries for 2D dielectric layers.
  #
  # Only dielectrics whose layer order falls within
  # (minimumconductorlayer, maximumconductorlayer + 1] are considered — i.e.
  # dielectrics that actually sit between/around conductor layers of interest.
  #
  # For each such dielectric:
  #   - If it has NO conductor intersections: it can be written as a single
  #     full-width block (bottom/side/top panels spanning the whole window).
  #     This branch is only executed when write_no_intersections == 1 (i.e.
  #     on the second, final pass — see extractFasterCapfile_2D), so all the
  #     "no intersection" dielectrics get written together at the end,
  #     after per-conductor-boundary dielectrics have already been written.
  #   - If it DOES intersect conductors: the dielectric is split into
  #     horizontal "row" strips (scanned in 0.01-unit increments) to find
  #     where conductors interrupt it, grouped into contiguous blocks
  #     (dielectricsgroups), and each block gets its own set of panels with
  #     boundaries positioned around the conductor gaps. This branch runs
  #     regardless of write_no_intersections (called on both passes), but is
  #     naturally gated by `len(intersections) != 0`.

  print(f"\tDEBUG: Writing Dielectrics")

  dielindex = 0
  first_dielectric_to_write_index = 0

  for intersections in dielintersections:
    if ("m" in PatternShapes[dielindexlist[dielindex]].name):
      dielectricororder = int(PatternShapes[dielindexlist[dielindex]].name.split("_")[0].split("m")[1])
    else:
      dielectricororder = -1
    
    if ((dielectricororder > minimumconductorlayer ) and (dielectricororder <= (maximumconductorlayer + 1))):
      # print(f"Considering dielectic: {PatternShapes[dielindexlist[dielindex]].name} ({dielectricororder} <= {(1+ maximumconductorlayer)})")
    # WRITE DIELECTRIC WITH NO INTERESECTION => THIS SHOULD BE WRITTEN IN THE END OF THE FASTERCAP FILE 
      if (len(intersections) == 0):
        # print(f"DEBUG (1): Dielectric {PatternShapes[dielindexlist[dielindex]].name} => no intersections, write all dielectric")
        
        if (write_no_intersections == 1):
          # create deielectric files covering the entire space #
          # create the plane for the dielectric if they are not exist covering the entire window for the 
          # specific thickness and insert the information into FasterCap pattern file

          if (groundconductorexists == 0):
            if (PatternShapes[dielindexlist[dielindex]].shapeorder == 0):
              
              FasterCapFile.write("* {} Dielectric\n".format(PatternShapes[dielindexlist[dielindex]].name))          
              FasterCapFile.write("*\n")  
              dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-bottom.txt"
              # print(f"DEBUG-2D: (2) Writting: {dielectricfile}")
              print(f"\t\tDEBUG: Writing {PatternShapes[dielindexlist[dielindex]].name} (ground plane does not exist and dielectric does not intersect with a conductor, order of dielectric = 0)")

              
              panel_io.write_dielectric_bottom_panel_2D(currentpath, dielectricfile, 
                                            PatternShapes[dielindexlist[dielindex]].name, 
                                            PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                            PatternShapes[dielindexlist[dielindex]].shapeheight
                                            )
              panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                                  dielectricfile, 
                                                  float(1.0e-6), 
                                                  round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8), 
                                                  PatternShapes[dielindexlist[dielindex]].shapex,
                                                  PatternShapes[dielindexlist[dielindex]].shapey,
                                                  round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                                  round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4)
                                                  )
            else:
              dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-bottom.txt"
              # print(f"DEBUG-2D: (2) Writting: {dielectricfile}")
              FasterCapFile.write("* {} Dielectric\n".format(PatternShapes[dielindexlist[dielindex]].name))          
              FasterCapFile.write("*\n")  
              print(f"\t\tDEBUG: Writing {PatternShapes[dielindexlist[dielindex]].name} (ground plane does not exist and dielectric does not intersect with a conductor, order of dielectric = {PatternShapes[dielindexlist[dielindex]].shapeorder})")


              panel_io.write_dielectric_bottom_panel_2D(currentpath, dielectricfile, 
                                            PatternShapes[dielindexlist[dielindex]].name, 
                                            PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                            PatternShapes[dielindexlist[dielindex]].shapeheight
                                            )
              panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                                dielectricfile, 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder - 1].epsilon) * float(1.0e-6), 8), 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8), 
                                                PatternShapes[dielindexlist[dielindex]].shapex,
                                                PatternShapes[dielindexlist[dielindex]].shapey,
                                                round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                                round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4)
                                                )

          dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-sides.txt"
          # print(f"DEBUG-2D: Writting side panel of {PatternShapes[dielindexlist[dielindex]].name} (2)")
          if (groundconductorexists == 1): # this if is used just for printing the name of the dielectric in the input file 
            FasterCapFile.write("* {} Dielectric\n".format(PatternShapes[dielindexlist[dielindex]].name))          
            FasterCapFile.write("*\n")  
            print(f"\t\tDEBUG: Writing side panels of {PatternShapes[dielindexlist[dielindex]].name} (ground plane exists and dielectric does not intersect with a conductor, order of dielectric = {PatternShapes[dielindexlist[dielindex]].shapeorder})")

          panel_io.write_dielectric_side_panels_2D(currentpath, dielectricfile, 
                                      PatternShapes[dielindexlist[dielindex]].name, 
                                      PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                      PatternShapes[dielindexlist[dielindex]].shapeheight
                                      )
          panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                              dielectricfile, 
                                              1.0e-6, 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              PatternShapes[dielindexlist[dielindex]].shapex,
                                              PatternShapes[dielindexlist[dielindex]].shapey,
                                              round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                              round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4)
                                              )
          
          if (dielindex < len(dielintersections) -1) and (PatternShapes[dielindexlist[dielindex]].contactwithplane == 0):
            print(f"\t\tDEBUG: Writing top panel of {PatternShapes[dielindexlist[dielindex]].name} (ground plane exists and dielectric does not intersect with a conductor, order of dielectric = {PatternShapes[dielindexlist[dielindex]].shapeorder})")

            dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapeheight)  + "-top.txt"
            panel_io.write_dielectric_top_panel_2D(currentpath, dielectricfile, 
                                      PatternShapes[dielindexlist[dielindex]].name, 
                                      PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                      PatternShapes[dielindexlist[dielindex]].shapeheight
                                      )
            panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                                dielectricfile, 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder + 1].epsilon) * float(1.0e-6), 8),
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                                PatternShapes[dielindexlist[dielindex]].shapex,
                                                PatternShapes[dielindexlist[dielindex]].shapey,
                                                round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                                round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4)
                                                )

          FasterCapFile.write("\n\n")

      else:
        # create dielectric files respecting the coordinates of conductors #
        # print(f"DEBUG-2D: Dielectric {PatternShapes[dielindexlist[dielindex]].name} has intersection with conductors")

        # Scan the dielectric's height in fixed 0.01-unit rows. For each row,
        # find the nearest intersecting conductor to the right of the current
        # scan position, and record that as the "starting point" for the
        # next scan of that row. Rows are then grouped into contiguous
        # (start_x, end_x, row_range) blocks wherever their intersection
        # boundary stays constant — this produces the list of open segments
        # of the dielectric layer not covered by a conductor.
        rowsstartingpoints = []
        rowsnumber = patternswindowheight / 0.01

        for i in range(int(rowsnumber)):
          rowsstartingpoints.append(window_min_x)

        dielectricsgroups = []
        groupindex = 0

        while (1):
          previousgroup_x = window_min_x
          
          # for each row have to find the intersection with conductor # 
          for i in range(int(rowsnumber)):

            row_x = rowsstartingpoints[i]
            row_y = 0.01 * i
            
            starting_row_x = row_x
            ending_row_x = window_max_x
            min_row_x_intersection = window_max_x

            # iterate through conductors #
            for conductor in dielintersections[dielindex]:
              
              conductor_x = PatternShapes[conductor].shapex
              conductor_y = PatternShapes[conductor].shapey

              conductor_h = PatternShapes[conductor].shapeheight
              conductor_w = PatternShapes[conductor].shapewidth

              if ((conductor_y <= row_y) and (conductor_y + conductor_h > row_y)):
                if (conductor_x > row_x):
                  if (min_row_x_intersection > conductor_x):
                    min_row_x_intersection = conductor_x + conductor_w
                    ending_row_x = conductor_x
            
            rowsstartingpoints[i] = min_row_x_intersection

            if (starting_row_x != window_max_x):
              if (i != 0):
                if (previousgroup_x == min_row_x_intersection):
                  dielectricsgroups[len(dielectricsgroups) - 1].append(i)
                else:
                  dielectricsgroups.append([])
                  dielectricsgroups[len(dielectricsgroups) - 1].append(starting_row_x)
                  dielectricsgroups[len(dielectricsgroups) - 1].append(ending_row_x)
                  dielectricsgroups[len(dielectricsgroups) - 1].append(i)
                  previousgroup_x = min_row_x_intersection
              else:
                previousgroup_x = min_row_x_intersection
                dielectricsgroups.append([])
            
                dielectricsgroups[len(dielectricsgroups) - 1].append(starting_row_x)
                dielectricsgroups[len(dielectricsgroups) - 1].append(ending_row_x)
                dielectricsgroups[len(dielectricsgroups) - 1].append(i)
            else:
              if (len(dielectricsgroups[len(dielectricsgroups) - 1]) != 0):
                previousgroup_x = window_min_x

          # loop again until every row's scan has reached window_max_x
          # (i.e. no more conductor-driven interruptions remain to resolve)
          finished = 1
          for i in range(int(rowsnumber)):
            row_x = rowsstartingpoints[i]
            if (row_x != window_max_x):
              finished = 0
              break
          
          if (finished == 1):
            break
        
        # print(f"diel blocks len = {len(dielectricsgroups)} for {PatternShapes[dielindexlist[dielindex]].name}")
        block_width = PatternShapes[dielindexlist[dielindex]].shapewidth
        block_height = PatternShapes[dielindexlist[dielindex]].shapeheight  
        block_x = PatternShapes[dielindexlist[dielindex]].shapex  
        block_y = PatternShapes[dielindexlist[dielindex]].shapey  

        if (write_no_intersections == 0):
          # Write one side-panel set covering the dielectric's full extent,
          # then one bottom/top panel per contiguous open block found above.
          dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_height) + "-sides.txt"
          # print(f"DEBUG-2D: Writting side panel of {PatternShapes[dielindexlist[dielindex]].name}")
          FasterCapFile.write("* {} Dielectric\n".format(PatternShapes[dielindexlist[dielindex]].name))          
          FasterCapFile.write("*\n") 
          panel_io.write_dielectric_side_panels_2D(currentpath, dielectricfile, 
                                      PatternShapes[dielindexlist[dielindex]].name, 
                                      block_width, 
                                      block_height
                                      )
          panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                              dielectricfile, 
                                              1.0e-6, 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              round(block_x, 4),
                                              round(block_y, 4),
                                              round(block_x + 0.01, 4),
                                              round(block_y + 0.01, 4)
                                              )
          
          for block in dielectricsgroups:

            # the height of the dielectric stays the same #
            # the sides panel should be printed only one time #
            # multiple top and bottom panels that start where there is an intersection #

            block_width = round(block[1] - block[0], 4)
            # print(f"BLOCK_WIDTH = {block_width}")
            if (block_width == PatternShapes[dielindexlist[dielindex]].shapewidth):
              # this block spans the entire width (i.e. no actual conductor
              # cut it), so it's redundant with the full-width panel already
              # written above -> skip
              continue
            # block_height = round(((block[-1] * 0.01) ) - (block[3] * 0.01), 4)

            block_x = block[0]
            block_y = PatternShapes[dielindexlist[dielindex]].shapey
            block_height = PatternShapes[dielindexlist[dielindex]].shapeheight  


            if (dielindex == 0):
              dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_height) + "-bottom.txt"
              # print(f"DEBUG-2D: Writting bottom panel of {PatternShapes[dielindexlist[dielindex]].name}")
              panel_io.write_dielectric_bottom_panel_2D(currentpath, dielectricfile, 
                                            PatternShapes[dielindexlist[dielindex]].name, 
                                            block_width,
                                            block_height
                                            )
              panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                                  dielectricfile, 
                                                  round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder - 1].epsilon) * float(1.0e-6), 8), 
                                                  round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8), 
                                                  round(block_x, 4),
                                                  round(block_y, 4),
                                                  round(block_x + 0.01, 4),
                                                  round(block_y + 0.01, 4)
                                                  )

            # dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_height)  + "-sides.txt"
            dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_height) + "-sides.txt"
            # print(f"DEBUG-2D: Writting side panel of {PatternShapes[dielindexlist[dielindex]].name}")

            if (dielindex < len(dielintersections) - 1):
              dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_height) + "-top.txt"
              panel_io.write_dielectric_top_panel_2D(currentpath, dielectricfile, 
                                        PatternShapes[dielindexlist[dielindex]].name, 
                                        block_width, 
                                        block_height
                                        )
              panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                                dielectricfile, 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder + 1].epsilon) * float(1.0e-6), 8),
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                                round(block_x, 4),
                                                round(block_y, 4),
                                                round(block_x + 0.01, 4),
                                                round(block_y + 0.01, 4)
                                                )

              # write bottom panel 
              if (first_dielectric):
                first_dielectric_to_write_index = dielindexlist[dielindex]
                dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_height) + "-bottom.txt"

                panel_io.write_dielectric_bottom_panel_2D(currentpath, dielectricfile, 
                                          PatternShapes[dielindexlist[dielindex]].name, 
                                          block_width, 
                                          block_height
                                          )
                panel_io.insert_dielectric_into_pattern_file_2D(currentpath, FasterCapFile, 
                                                  dielectricfile, 
                                                  round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder - 1 ].epsilon) * float(1.0e-6), 8),
                                                  round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                                  round(block_x, 4),
                                                  round(block_y, 4),
                                                  round(block_x + 0.01, 4),
                                                  round(block_y + 0.01, 4)
                                                  )
          first_dielectric = 0

          FasterCapFile.write("\n\n")
    
    dielindex += 1

  

def extractFasterCapfile_2D(filename: str): 
  # Main 2D file-writing orchestrator: given the already-populated
  # PatternShapes list (from TranslateUniversalFile), determines which
  # conductors intersect which dielectrics (and vice versa), then writes
  # the full FasterCap .lst file in sections: dielectrics-with-intersections,
  # conductors, ground planes, then the remaining (non-intersecting)
  # dielectric "process stack".
  print("---------------------------------------") 
  print("INFO: Extracting the FasterCap input file for 2D")
  print("---------------------------------------") 

  if (not os.path.exists(os.path.join(currentpath, "Dielectrics"))):
    os.makedirs(os.path.join(currentpath, "Dielectrics"))

  if (not os.path.exists(os.path.join(currentpath, "Wires"))):
    os.makedirs(os.path.join(currentpath, "Wires"))

  # create the Dielectrics Stack as no other conductor exist //

  index = 0
  FasterCapFile = open(filename, "w+")

  conductorindexlist = []
  conductorsintersections = []

  dielindexlist = []
  dielintersections = []

  # Iterates all of the shapes (wires & dielectrics)
  # Builds two parallel index structures:
  #   dielindexlist / dielintersections    -> for each dielectric shape,
  #                                            which conductor shapes it
  #                                            vertically overlaps
  #   conductorindexlist / conductorsintersections -> for each conductor
  #                                            shape, which dielectric
  #                                            shapes it vertically overlaps
  # Overlap is tested purely on the y-axis (shapey / shapeheight), since in
  # 2D mode all shapes already share the same width axis.
  print(f"\tDEBUG: Find the intersection of the conductors with each dielectric")
  for shape in PatternShapes:

    if (shape.shapetype == 0):      
      # if the current shape is a conductor , iterate over the conductors of the shape database #
      condintersect = []

      for j in range(len(PatternShapes)):

        if (PatternShapes[j].shapetype == 1): # WIRES #
          if (shape.shapey >= PatternShapes[j].shapey + PatternShapes[j].shapeheight):
            continue
          elif (shape.shapey == PatternShapes[j].shapey):
            print(f"\t\tDEBUG: Dielectric {shape.name} intersects with conductor {PatternShapes[j].name}")
            condintersect.append(j)
          elif (shape.shapey < PatternShapes[j].shapey):
            continue
          elif (shape.shapey < PatternShapes[j].shapey + PatternShapes[j].shapeheight):
            print(f"\t\tDEBUG: Dielectric {shape.name} intersects with conductor {PatternShapes[j].name}")
            condintersect.append(j)
          else:
            break
        else:
          continue

      dielindexlist.append(index)
      dielintersections.append(condintersect)
        
    else:
      print(f"\tDEBUG: Find the intersection of the dielectrics with each conductor")
      
      dielintersect = []
      for j in range(len(PatternShapes)):
        
        if (PatternShapes[j].shapetype == 0):
          if (shape.shapey > PatternShapes[j].shapey):
            continue
          elif (shape.shapey == PatternShapes[j].shapey):
            print(f"\t\tDEBUG: Conductor {shape.name} intersects with dielectric {PatternShapes[j].name}")

            dielintersect.append(j)
          elif (shape.shapey + shape.shapeheight > PatternShapes[j].shapey):
            print(f"\t\tDEBUG: Conductor {shape.name} intersects with dielectric {PatternShapes[j].name}")
            dielintersect.append(j)
          else:
            break
        else:
          continue

      conductorindexlist.append(index)
      conductorsintersections.append(dielintersect)

    if (shape.groundplane == 1):

      print(f"\tDEBUG: Find the intersection of the ground planes with each dielectric")

      # Flag any dielectric that touches this ground plane exactly at its
      # top boundary (shape.shapey == dielectric top edge), so that
      # write_dielectrics_2D can avoid emitting a duplicate/overlapping
      # top panel for it.
      for j in range(len(PatternShapes)):
        # print(f"\t\tDEBUG: Ground Plane {shape.name} [y = {shape.shapey}] - dielectric {PatternShapes[j].name} [y + height = {(PatternShapes[j].shapey + PatternShapes[j].shapeheight)}]")
        
        if (PatternShapes[j].shapetype == 0): # DIELECTRICS #
          if (shape.shapey == (PatternShapes[j].shapey + PatternShapes[j].shapeheight)):
            PatternShapes[j].contactwithplane = 1
            # This is neeeded, otherwise FasterCap gets overlapping panels #


    index += 1

  conductorindex = 0
  groundconductorexists = 0
  minimumconductorlayer = 10
  maximumconductorlayer = 0

  print("---------------------------------------")
  print(f"DEBUG: Shapes")
  print("---------------------------------------")    
  for i in range(len(PatternShapes)):
    PatternShapes[i].print_contents()
  print("---------------------------------------")
  print(f"DEBUG: End of Shapes")
  print("---------------------------------------")    
  
  # FasterCapFile.write("* ------------------------------\n")          
  FasterCapFile.write("* 2D Pattern\n") 
  FasterCapFile.write("* ------------------------------\n\n")          


  FasterCapFile.write("* ------------------------------\n")          
  FasterCapFile.write("* Dielectrics with intersections\n")          
  FasterCapFile.write("* ------------------------------\n\n")          

  print("---------------------------------------")
  print(f"INFO: Writing Dielectrics with intersections")
  print("---------------------------------------")

  # Pass 1 (write=0): dry-run over conductors purely to compute
  # minimumconductorlayer / maximumconductorlayer bounds needed by
  # write_dielectrics_2D below.
  groundconductorexists, minimumconductorlayer, maximumconductorlayer = write_conductors_2D(minimumconductorlayer, maximumconductorlayer, conductorsintersections, conductorindexlist, dielindexlist, FasterCapFile, 0, 0)


  dielindex = 0
  first_dielectric = 1
  # Write dielectrics that DO intersect conductors first (write_no_intersections=0)
  write_dielectrics_2D(first_dielectric, dielintersections, dielindexlist, minimumconductorlayer, maximumconductorlayer, groundconductorexists, FasterCapFile, 0)
  
  FasterCapFile.write("* ------------------------------\n")          
  FasterCapFile.write("* Conductors\n")          
  FasterCapFile.write("* ------------------------------\n\n")  

  print("---------------------------------------")
  print(f"INFO: Writing Conductors")
  print("---------------------------------------")        
  # Pass 2 (write=1, ground=0): actually write ordinary conductor panels
  groundconductorexists, minimumconductorlayer, maximumconductorlayer = write_conductors_2D(minimumconductorlayer, maximumconductorlayer, conductorsintersections, conductorindexlist, dielindexlist, FasterCapFile, 1, 0)
  
  FasterCapFile.write("* ------------------------------\n")          
  FasterCapFile.write("* Ground\n")          
  FasterCapFile.write("* ------------------------------\n\n")    

  print("---------------------------------------")
  print(f"INFO: Writing Ground Planes")
  print("---------------------------------------")   
  write_ground_planes_2D(minimumconductorlayer, maximumconductorlayer, conductorsintersections, conductorindexlist, dielindexlist, FasterCapFile, 1, 1)
  # groundconductorexists, minimumconductorlayer, maximumconductorlayer = write_conductors_2D(minimumconductorlayer, maximumconductorlayer, conductorsintersections, conductorindexlist, dielindexlist, FasterCapFile, 1, 1)
  
  FasterCapFile.write("* ------------------------------\n")          
  FasterCapFile.write("* Process Stack\n")          
  FasterCapFile.write("* ------------------------------\n\n")          
 
  print("---------------------------------------")
  print(f"INFO: Writing Process Stack")
  print("---------------------------------------")   
  # Final pass: write dielectrics that had NO conductor intersections
  # (write_no_intersections=1), i.e. the remaining "background" dielectric stack.
  write_dielectrics_2D(first_dielectric, dielintersections, dielindexlist, minimumconductorlayer, maximumconductorlayer, groundconductorexists, FasterCapFile, 1)


  FasterCapFile.close()

def extractFasterCapfile(filename: str):  
  # 3D counterpart of extractFasterCapfile_2D. Same overall structure —
  # compute conductor/dielectric intersections, then write conductor and
  # dielectric panels — but working in 3D (y = "thickness" axis here, per
  # the LL corner y<->z swap used when PatternShapes were built), and without
  # the separate ground-plane / row-scanning logic the 2D path uses (3D
  # dielectric splitting is done directly via the intersection index lists
  # below, block-by-block, rather than a row-scan).
  
  # for i in range(len(PatternShapes)):
  #   PatternShapes[i].print_contents()

  if (not os.path.exists(os.path.join(currentpath, "Dielectrics"))):
    os.makedirs(os.path.join(currentpath, "Dielectrics"))

  if (not os.path.exists(os.path.join(currentpath, "Wires"))):
    os.makedirs(os.path.join(currentpath, "Wires"))

  # create the Dielectrics Stack as no other conductor exist //
  
  # PatternShapes.sort(key = operator.attrgetter('shapey'))
  
  index = 0
  FasterCapFile = open(filename, "w+")

  conductorindexlist = []
  conductorsintersections = []

  dielindexlist = []
  dielintersections = []

  # Build dielectric<->conductor intersection index lists, same approach as
  # extractFasterCapfile_2D but comparing shapey against shapethickness
  # (the 3D "vertical" extent) instead of shapeheight.
  for shape in PatternShapes:

    if (shape.shapetype == 0):      
      condintersect = []

      for j in range(len(PatternShapes)):
        
        if (PatternShapes[j].shapetype == 1):
          if (shape.shapey >= PatternShapes[j].shapey + PatternShapes[j].shapethickness):
            continue
          elif (shape.shapey == PatternShapes[j].shapey):
            condintersect.append(j)
          elif (shape.shapey < PatternShapes[j].shapey):
            continue
          elif (shape.shapey < PatternShapes[j].shapey + PatternShapes[j].shapethickness):
            condintersect.append(j)
          else:
            break
        else:
          #print(shape.name)
          continue
      
      dielindexlist.append(index)
      dielintersections.append(condintersect)
        
    else:
      
      dielintersect = []
      for j in range(len(PatternShapes)):
        
        if (PatternShapes[j].shapetype == 0):
          if (shape.shapey > PatternShapes[j].shapey):
            continue
          elif (shape.shapey == PatternShapes[j].shapey):
            dielintersect.append(j)
          elif (shape.shapey + shape.shapethickness > PatternShapes[j].shapey):
            dielintersect.append(j)
          else:
            break
        else:
          #print(shape.name)
          continue
      
      conductorindexlist.append(index)
      conductorsintersections.append(dielintersect)

    index += 1

  conductorindex = 0
  groundconductorexists = 0
  minimumconductorlayer = 10
  maximumconductorlayer = 0
  # --- Write conductor panels ---
  # For each conductor: if it has no dielectric intersections, write
  # bottom/side/top panels directly (default 1e-6 outer permittivity,
  # base_epsilon-scaled inner). If it does intersect dielectrics, write one
  # side panel per intersecting dielectric layer (using that layer's
  # epsilon), plus a bottom panel (using the first intersection's epsilon)
  # and a top panel (using the epsilon one layer above the last intersection).
  for intersectionslist in conductorsintersections:

    conductororder = int(PatternShapes[conductorindexlist[conductorindex]].name.split("_")[0].split("M")[1])
    
    if (conductororder < minimumconductorlayer):
      minimumconductorlayer = conductororder
    
    if (conductororder > maximumconductorlayer):
      maximumconductorlayer = conductororder
      
    if (len(intersectionslist) == 0):
      groundconductorexists = 1
      conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapethickness) + "_H" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-bottom.txt"
      panel_io.write_wire_bottom_panel(currentpath, conductorfile, 
                              PatternShapes[conductorindexlist[conductorindex]].name, 
                              PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                              PatternShapes[conductorindexlist[conductorindex]].shapethickness, 
                              PatternShapes[conductorindexlist[conductorindex]].shapeheight
                              )
      panel_io.insert_conductor_into_pattern_file(currentpath, FasterCapFile, 
                                        conductorfile,
                                        float(1.0e-6),
                                        PatternShapes[conductorindexlist[conductorindex]].shapex,
                                        PatternShapes[conductorindexlist[conductorindex]].shapey,
                                        PatternShapes[conductorindexlist[conductorindex]].shapez,
                                        )
      FasterCapFile.write(" + \n")

      conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapethickness) + "_H" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-sides.txt"
      panel_io.write_wire_side_panels(currentpath, conductorfile, 
                            PatternShapes[conductorindexlist[conductorindex]].name, 
                            PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                            PatternShapes[conductorindexlist[conductorindex]].shapethickness, 
                            PatternShapes[conductorindexlist[conductorindex]].shapeheight
                            )
      panel_io.insert_conductor_into_pattern_file(currentpath, FasterCapFile, 
                                          conductorfile,
                                          float(1.0e-6),
                                          PatternShapes[conductorindexlist[conductorindex]].shapex,
                                          PatternShapes[conductorindexlist[conductorindex]].shapey,
                                          PatternShapes[conductorindexlist[conductorindex]].shapez,
                                          )
      FasterCapFile.write(" + \n")

      conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[conductorindexlist[conductorindex]].shapethickness) + "_H" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-top.txt"
      panel_io.write_wire_top_panel(currentpath, conductorfile, 
                          PatternShapes[conductorindexlist[conductorindex]].name, 
                          PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                          PatternShapes[conductorindexlist[conductorindex]].shapethickness, 
                          PatternShapes[conductorindexlist[conductorindex]].shapeheight
                          )
      panel_io.insert_conductor_into_pattern_file(currentpath, FasterCapFile, 
                                        conductorfile,
                                        round(base_epsilon * float(1e-6), 8),
                                        PatternShapes[conductorindexlist[conductorindex]].shapex,
                                        PatternShapes[conductorindexlist[conductorindex]].shapey,
                                        PatternShapes[conductorindexlist[conductorindex]].shapez,
                                        )
      FasterCapFile.write("\n\n")

    else:
      intersectiondiel = 0
      
      for intersection in intersectionslist:

        if (intersectiondiel == 0):
          conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[intersection].shapethickness) + "_H" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-bottom.txt"
          panel_io.write_wire_bottom_panel(currentpath, conductorfile, 
                                  PatternShapes[conductorindexlist[conductorindex]].name, 
                                  PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                                  PatternShapes[intersection].shapethickness, 
                                  PatternShapes[conductorindexlist[conductorindex]].shapeheight
                                  )
          panel_io.insert_conductor_into_pattern_file(currentpath, FasterCapFile, 
                                            conductorfile,
                                            round(float(processDielectrics[PatternShapes[dielindexlist[intersection]].shapeorder].epsilon) * float(1.0e-6), 8),
                                            PatternShapes[conductorindexlist[conductorindex]].shapex,
                                            PatternShapes[intersection].shapey,
                                            PatternShapes[conductorindexlist[conductorindex]].shapez,
                                            )
          FasterCapFile.write(" + \n")


        conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[intersection].shapethickness) + "_H" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-sides.txt"
        panel_io.write_wire_side_panels(currentpath, conductorfile, 
                              PatternShapes[conductorindexlist[conductorindex]].name, 
                              PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                              PatternShapes[intersection].shapethickness, 
                              PatternShapes[conductorindexlist[conductorindex]].shapeheight
                              )
        panel_io.insert_conductor_into_pattern_file(currentpath, FasterCapFile, 
                                            conductorfile,
                                            round(float(processDielectrics[PatternShapes[dielindexlist[intersection]].shapeorder].epsilon) * float(1.0e-6), 8),
                                            PatternShapes[conductorindexlist[conductorindex]].shapex,
                                            PatternShapes[intersection].shapey,
                                            PatternShapes[conductorindexlist[conductorindex]].shapez,
                                            )
        FasterCapFile.write(" + \n")

        if (intersectiondiel == len(intersectionslist) - 1):
          conductorfile = "Wires/wire_" + PatternShapes[conductorindexlist[conductorindex]].name + "_W" + str(PatternShapes[conductorindexlist[conductorindex]].shapewidth) + "_T" + str(PatternShapes[intersection].shapethickness) + "_H" + str(PatternShapes[conductorindexlist[conductorindex]].shapeheight) + "-top.txt"
          panel_io.write_wire_top_panel(currentpath, conductorfile, 
                              PatternShapes[conductorindexlist[conductorindex]].name, 
                              PatternShapes[conductorindexlist[conductorindex]].shapewidth, 
                              PatternShapes[intersection].shapethickness, 
                              PatternShapes[conductorindexlist[conductorindex]].shapeheight
                              )
          panel_io.insert_conductor_into_pattern_file(currentpath, FasterCapFile, 
                                            conductorfile,
                                            round(float(processDielectrics[PatternShapes[dielindexlist[intersection]].shapeorder + 1].epsilon) * float(1.0e-6), 8),
                                            PatternShapes[conductorindexlist[conductorindex]].shapex,
                                            PatternShapes[intersection].shapey,
                                            PatternShapes[conductorindexlist[conductorindex]].shapez,
                                            )
          FasterCapFile.write("\n\n")

        intersectiondiel += 1
    conductorindex += 1

  # print(f"DEBUG-TSILI: maximumconductorlayer = {maximumconductorlayer}, minimumconductorlayer = {minimumconductorlayer}")
  # --- Write dielectric panels ---
  # Only dielectrics whose layer order falls between minimumconductorlayer
  # and maximumconductorlayer (inclusive) are written, same filtering
  # principle as write_dielectrics_2D.
  dielindex = 0
  for intersections in dielintersections:

    if ("m" in PatternShapes[dielindexlist[dielindex]].name):
      dielectricororder = int(PatternShapes[dielindexlist[dielindex]].name.split("_")[0].split("m")[1])
    else:
      dielectricororder = 0

    if True:
    # if ((dielectricororder >= minimumconductorlayer) and (dielectricororder <= maximumconductorlayer)):
      if (len(intersections) == 0):
        # create deielectric files covering the entire space #
        # create the plane for the dielectric if they are not exist covering the entire window for the 
        # specific thickness and insert the information into FasterCap pattern file

        if (groundconductorexists == 0):
          if (PatternShapes[dielindexlist[dielindex]].shapeorder == 0):
            dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapethickness) + "_H" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-bottom.txt"
            panel_io.write_dielectric_bottom_panel(currentpath, dielectricfile, 
                                          PatternShapes[dielindexlist[dielindex]].name, 
                                          PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                          PatternShapes[dielindexlist[dielindex]].shapethickness, 
                                          PatternShapes[dielindexlist[dielindex]].shapeheight
                                          )
            panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                                dielectricfile, 
                                                float(1.0e-6), 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8), 
                                                PatternShapes[dielindexlist[dielindex]].shapex,
                                                PatternShapes[dielindexlist[dielindex]].shapey,
                                                0.0,
                                                round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                                round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4),
                                                0.0 + 0.01
                                                )
          else:
            dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapethickness) + "_H" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-bottom.txt"
            panel_io.write_dielectric_bottom_panel(currentpath, dielectricfile, 
                                          PatternShapes[dielindexlist[dielindex]].name, 
                                          PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                          PatternShapes[dielindexlist[dielindex]].shapethickness, 
                                          PatternShapes[dielindexlist[dielindex]].shapeheight
                                          )
            panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                              dielectricfile, 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder - 1].epsilon) * float(1.0e-6), 8), 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8), 
                                              PatternShapes[dielindexlist[dielindex]].shapex,
                                              PatternShapes[dielindexlist[dielindex]].shapey,
                                              0.0,
                                              round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                              round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4),
                                              0.0 + 0.01
                                              )

        dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapethickness) + "_H" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-sides.txt"
        panel_io.write_dielectric_side_panels(currentpath, dielectricfile, 
                                    PatternShapes[dielindexlist[dielindex]].name, 
                                    PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                    PatternShapes[dielindexlist[dielindex]].shapethickness, 
                                    PatternShapes[dielindexlist[dielindex]].shapeheight
                                    )
        panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                            dielectricfile, 
                                            1.0e-6, 
                                            round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                            PatternShapes[dielindexlist[dielindex]].shapex,
                                            PatternShapes[dielindexlist[dielindex]].shapey,
                                            0.0,
                                            round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                            round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4),
                                            0.0 + 0.01
                                            )
        
        if (dielindex < len(dielintersections) -1):
          dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(PatternShapes[dielindexlist[dielindex]].shapewidth) + "_T" + str(PatternShapes[dielindexlist[dielindex]].shapethickness) + "_H" + str(PatternShapes[dielindexlist[dielindex]].shapeheight) + "-top.txt"
          panel_io.write_dielectric_top_panel(currentpath, dielectricfile, 
                                    PatternShapes[dielindexlist[dielindex]].name, 
                                    PatternShapes[dielindexlist[dielindex]].shapewidth, 
                                    PatternShapes[dielindexlist[dielindex]].shapethickness, 
                                    PatternShapes[dielindexlist[dielindex]].shapeheight
                                    )
          panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                              dielectricfile, 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder + 1].epsilon) * float(1.0e-6), 8),
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              PatternShapes[dielindexlist[dielindex]].shapex,
                                              PatternShapes[dielindexlist[dielindex]].shapey,
                                              0.0,
                                              round(PatternShapes[dielindexlist[dielindex]].shapex + 0.01, 4),
                                              round(PatternShapes[dielindexlist[dielindex]].shapey + 0.01, 4),
                                              0.0 + 0.01
                                              )

        FasterCapFile.write("\n\n")

      else:
        # create dielectric files respecting the coordinates of conductors #
        # Same row-scan-and-group strategy as write_dielectrics_2D, but
        # scanning rows across patternswindowheight (the z-axis in 3D) and
        # tracking conductor x/z position + width/height instead of x/y.
        rowsstartingpoints = []
        rowsnumber = patternswindowheight / 0.01

        for i in range(int(rowsnumber)):
          rowsstartingpoints.append(window_min_x)

        dielectricsgroups = []
        groupindex = 0

        while (1):
          previousgroup_x = window_min_x
          
          # for each row have to find the intersection with conductor # 
          for i in range(int(rowsnumber)):

            row_x = rowsstartingpoints[i]
            row_z = 0.01 * i
            
            starting_row_x = row_x
            ending_row_x = window_max_x
            min_row_x_intersection = window_max_x

            # iterate through conductors #
            for conductor in dielintersections[dielindex]:
              conductor_x = PatternShapes[conductor].shapex
              conductor_z = PatternShapes[conductor].shapez

              conductor_h = PatternShapes[conductor].shapeheight
              conductor_w = PatternShapes[conductor].shapewidth

              if ((conductor_z <= row_z) and (conductor_z + conductor_h > row_z)):
                if (conductor_x > row_x):
                  if (min_row_x_intersection > conductor_x):
                    min_row_x_intersection = conductor_x + conductor_w
                    ending_row_x = conductor_x
            
            rowsstartingpoints[i] = min_row_x_intersection

            if (starting_row_x != window_max_x):
              if (i != 0):
                if (previousgroup_x == min_row_x_intersection):
                  dielectricsgroups[len(dielectricsgroups) - 1].append(i)
                else:
                  dielectricsgroups.append([])
                  dielectricsgroups[len(dielectricsgroups) - 1].append(starting_row_x)
                  dielectricsgroups[len(dielectricsgroups) - 1].append(ending_row_x)
                  dielectricsgroups[len(dielectricsgroups) - 1].append(i)
                  previousgroup_x = min_row_x_intersection
              else:
                previousgroup_x = min_row_x_intersection
                dielectricsgroups.append([])
                dielectricsgroups[len(dielectricsgroups) - 1].append(starting_row_x)
                dielectricsgroups[len(dielectricsgroups) - 1].append(ending_row_x)
                dielectricsgroups[len(dielectricsgroups) - 1].append(i)
            else:
              if (len(dielectricsgroups[len(dielectricsgroups) - 1]) != 0):
                previousgroup_x = window_min_x

          finished = 1
          for i in range(int(rowsnumber)):
            row_x = rowsstartingpoints[i]
            if (row_x != window_max_x):
              finished = 0
              break
          
          if (finished == 1):
            break
        
        # For each contiguous open block found by the row scan, write
        # bottom (first dielectric only) / side / top panels sized and
        # positioned to that block.
        for block in dielectricsgroups:

          block_width = round(block[1] - block[0], 4)
          block_height = round((block[-1] * 0.01) - (block[3] * 0.01), 4)
          block_thickness = PatternShapes[dielindexlist[dielindex]].shapethickness

          block_x = block[0]
          block_y = PatternShapes[dielindexlist[dielindex]].shapey
          block_z = round(block[3] * 0.01, 4)

          if (dielindex == 0):
            dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_thickness) + "_H" + str(block_height) + "-bottom.txt"
            panel_io.write_dielectric_bottom_panel(currentpath, dielectricfile, 
                                          PatternShapes[dielindexlist[dielindex]].name, 
                                          block_width, 
                                          block_thickness, 
                                          block_height
                                          )
            panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                                dielectricfile, 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder - 1].epsilon) * float(1.0e-6), 8), 
                                                round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8), 
                                                round(block_x, 4),
                                                round(block_y, 4),
                                                round(block_z, 4),
                                                round(block_x + 0.01, 4),
                                                round(block_y + 0.01, 4),
                                                round(block_z + 0.01, 4),
                                                )

          dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_thickness) + "_H" + str(block_height) + "-sides.txt"
          panel_io.write_dielectric_side_panels(currentpath, dielectricfile, 
                                      PatternShapes[dielindexlist[dielindex]].name, 
                                      block_width, 
                                      block_thickness, 
                                      block_height
                                      )
          panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                              dielectricfile, 
                                              1.0e-6, 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              round(block_x, 4),
                                              round(block_y, 4),
                                              round(block_z, 4),
                                              round(block_x + 0.01, 4),
                                              round(block_y + 0.01, 4),
                                              round(block_z + 0.01, 4),
                                              )
          
          if (dielindex < len(dielintersections) -1):
            dielectricfile = "Dielectrics/dielectric_" + PatternShapes[dielindexlist[dielindex]].name + "_W" + str(block_width) + "_T" + str(block_thickness) + "_H" + str(block_height) + "-top.txt"
            panel_io.write_dielectric_top_panel(currentpath, dielectricfile, 
                                      PatternShapes[dielindexlist[dielindex]].name, 
                                      block_width, 
                                      block_thickness, 
                                      block_height
                                      )
            panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, 
                                              dielectricfile, 
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder + 1].epsilon) * float(1.0e-6), 8),
                                              round(float(processDielectrics[PatternShapes[dielindexlist[dielindex]].shapeorder].epsilon) * float(1.0e-6), 8),
                                              round(block_x, 4),
                                              round(block_y, 4),
                                              round(block_z, 4),
                                              round(block_x + 0.01, 4),
                                              round(block_y + 0.01, 4),
                                              round(block_z + 0.01, 4),
                                              )


        FasterCapFile.write("\n\n")
    dielindex += 1

  FasterCapFile.close()

# Layered 3D writer #
# Every surface is written once:
#   - the interface between two dielectrics, over the whole window, minus the
#     footprints of the conductors at that height
#   - the window walls of each dielectric, vacuum outside, minus the faces of
#     conductors lying on the wall
#   - each conductor face, split at the dielectric heights, with the
#     permittivity of the medium in front of it
# Coordinates follow PatternShapes: x = x, y = height, z = length.
LAYERED_TOLERANCE = 1e-6
LAYERED_PROBE = 1e-4 # distance of the point probed in front of a face #
LAYERED_VOID = 1.0e-6 # vacuum, permittivities are scaled by 1e-6 (um geometry) #

def layered_scaled_epsilon(epsilon):
  return round(float(epsilon) * float(1e-6), 8)

def layered_split_rectangle(u0, u1, v0, v1, holes):
  # Rectangle [u0, u1] x [v0, v1] minus the rectangles in holes, as a list
  # of rectangles on the grid of all hole edges #
  us = sorted({u0, u1} | {u for hole in holes for u in hole[0:2] if u0 < u < u1})
  vs = sorted({v0, v1} | {v for hole in holes for v in hole[2:4] if v0 < v < v1})
  cells = []
  for i in range(len(us) - 1):
    for j in range(len(vs) - 1):
      cu = (us[i] + us[i + 1]) / 2
      cv = (vs[j] + vs[j + 1]) / 2
      if not any(hole[0] < cu < hole[1] and hole[2] < cv < hole[3] for hole in holes):
        cells.append((us[i], us[i + 1], vs[j], vs[j + 1]))
  return cells

def layered_medium(domain, layers, x, y, z):
  # Scaled permittivity at a point: vacuum outside the window, otherwise the
  # dielectric at height y #
  x0, x1, y0, y1, z0, z1 = domain
  if not (x0 < x < x1 and y0 < y < y1 and z0 < z < z1):
    return LAYERED_VOID
  for ylow, yhigh, epsilon, name in layers:
    if ylow <= y < yhigh:
      return epsilon
  return LAYERED_VOID

def layered_quad_xz(x0, x1, z0, z1, y):
  return [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]

def layered_quad_zy(z0, z1, y0, y1, x):
  return [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]

def layered_quad_xy(x0, x1, y0, y1, z):
  return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]

def layered_write_panels(filename, name, quads):
  # One panel file in absolute coordinates, inserted with offset 0 0 0 #
  file = open(os.path.join(currentpath, filename), "w+")
  file.write("* {}\n".format(name))
  file.write("* face name	| four coordinates of one face\n\n")
  for quad in quads:
    file.write("Q {}  ".format(name) + "     ".join("{} {} {}".format(*point) for point in quad) + "\n")
  file.close()

def layered_conductor_faces(box, domain, layers):
  # Faces of a conductor box grouped by the scaled permittivity in front of
  # them, probed at a point just outside each face #
  x0, x1, y0, y1, z0, z1 = box
  cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
  faces_and_probes = [
    (layered_quad_xz(x0, x1, z0, z1, y0), (cx, y0 - LAYERED_PROBE, cz)), # bottom #
    (layered_quad_xz(x0, x1, z0, z1, y1), (cx, y1 + LAYERED_PROBE, cz)), # top #
  ]

  # vertical faces, split at every dielectric height #
  heights = sorted({y0, y1} | {y for layer in layers for y in layer[0:2] if y0 < y < y1})
  for ya, yb in zip(heights[:-1], heights[1:]):
    cy = (ya + yb) / 2
    faces_and_probes += [
      (layered_quad_zy(z0, z1, ya, yb, x0), (x0 - LAYERED_PROBE, cy, cz)),
      (layered_quad_zy(z0, z1, ya, yb, x1), (x1 + LAYERED_PROBE, cy, cz)),
      (layered_quad_xy(x0, x1, ya, yb, z0), (cx, cy, z0 - LAYERED_PROBE)),
      (layered_quad_xy(x0, x1, ya, yb, z1), (cx, cy, z1 + LAYERED_PROBE)),
    ]

  faces = {}
  for quad, probe in faces_and_probes:
    faces.setdefault(layered_medium(domain, layers, *probe), []).append(quad)
  return faces

def extractFasterCapfile_layered(filename: str):
  for folder in ("Dielectrics", "Wires"):
    if (not os.path.exists(os.path.join(currentpath, folder))):
      os.makedirs(os.path.join(currentpath, folder))

  # panel files of all patterns share Dielectrics/ and Wires/ #
  prefix = os.path.relpath(os.path.dirname(filename), currentpath).replace(os.sep, "_")

  dielectrics = sorted([shape for shape in PatternShapes if shape.shapetype == 0], key=attrgetter('shapey'))
  conductors = [shape for shape in PatternShapes if shape.shapetype == 1]
  if len(dielectrics) == 0:
    print(f"ERROR! {filename}: no DIELECTRIC, the layered writer needs at least one")
    sys.exit(-2)

  layers = []
  for shape in dielectrics:
    ylow = round(shape.shapey, 6)
    yhigh = round(shape.shapey + shape.shapethickness, 6)
    layers.append((ylow, yhigh, layered_scaled_epsilon(shape.epsilon), shape.name))

  first = dielectrics[0]
  x0 = round(first.shapex, 6)
  x1 = round(first.shapex + first.shapewidth, 6)
  z0 = round(first.shapez, 6)
  z1 = round(first.shapez + first.shapeheight, 6)
  domain = (x0, x1, layers[0][0], layers[-1][1], z0, z1)
  xmid, zmid = (x0 + x1) / 2, (z0 + z1) / 2

  boxes = []
  for shape in conductors:
    boxes.append((shape.name, (round(shape.shapex, 6), round(shape.shapex + shape.shapewidth, 6),
                               round(shape.shapey, 6), round(shape.shapey + shape.shapethickness, 6),
                               round(shape.shapez, 6), round(shape.shapez + shape.shapeheight, 6))))

  FasterCapFile = open(filename, "w+")

  # Conductors: one C record per permittivity in front of the faces
  for name, box in boxes:
    faces = layered_conductor_faces(box, domain, layers)
    records = []
    for index, (epsilon, quads) in enumerate(sorted(faces.items())):
      conductorfile = "Wires/{}_{}_{}.txt".format(prefix, name, index)
      layered_write_panels(conductorfile, name, quads)
      records.append("C {}/{}   {}    0.0 0.0 0.0 ".format(currentpath, conductorfile, epsilon))
    FasterCapFile.write(" + \n".join(records) + "\n\n")

  # Dielectrics
  for index, (ylow, yhigh, epsilon, name) in enumerate(layers):
    reference = (xmid, (ylow + yhigh) / 2, zmid) # a point inside this dielectric #

    # bottom of the window, unless a conductor (the ground plane) covers it #
    if index == 0:
      holes = [(b[0], b[1], b[4], b[5]) for _, b in boxes if b[2] - LAYERED_TOLERANCE <= ylow <= b[3] + LAYERED_TOLERANCE]
      quads = [layered_quad_xz(*cell, ylow) for cell in layered_split_rectangle(x0, x1, z0, z1, holes)]
      if quads:
        dielectricfile = "Dielectrics/{}_{}-bottom.txt".format(prefix, name)
        layered_write_panels(dielectricfile, name, quads)
        panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, dielectricfile, LAYERED_VOID, epsilon, 0.0, 0.0, 0.0, *reference)

    # window walls, vacuum outside #
    quads = []
    for x in (x0, x1):
      holes = [(b[4], b[5], b[2], b[3]) for _, b in boxes if abs(b[0] - x) < LAYERED_TOLERANCE or abs(b[1] - x) < LAYERED_TOLERANCE]
      quads += [layered_quad_zy(*cell, x) for cell in layered_split_rectangle(z0, z1, ylow, yhigh, holes)]
    for z in (z0, z1):
      holes = [(b[0], b[1], b[2], b[3]) for _, b in boxes if abs(b[4] - z) < LAYERED_TOLERANCE or abs(b[5] - z) < LAYERED_TOLERANCE]
      quads += [layered_quad_xy(*cell, z) for cell in layered_split_rectangle(x0, x1, ylow, yhigh, holes)]
    if quads:
      dielectricfile = "Dielectrics/{}_{}-sides.txt".format(prefix, name)
      layered_write_panels(dielectricfile, name, quads)
      panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, dielectricfile, LAYERED_VOID, epsilon, 0.0, 0.0, 0.0, *reference)

    # top: interface with the dielectric above, or vacuum above the window #
    # (no surface between two dielectrics of the same permittivity) #
    above = layers[index + 1][2] if index + 1 < len(layers) else LAYERED_VOID
    holes = [(b[0], b[1], b[4], b[5]) for _, b in boxes if b[2] - LAYERED_TOLERANCE <= yhigh <= b[3] + LAYERED_TOLERANCE]
    quads = [layered_quad_xz(*cell, yhigh) for cell in layered_split_rectangle(x0, x1, z0, z1, holes)]
    if quads and above != epsilon:
      dielectricfile = "Dielectrics/{}_{}-top.txt".format(prefix, name)
      layered_write_panels(dielectricfile, name, quads)
      panel_io.insert_dielectric_into_pattern_file(currentpath, FasterCapFile, dielectricfile, above, epsilon, 0.0, 0.0, 0.0, *reference)

    FasterCapFile.write("\n")

  FasterCapFile.close()

def main (argv):
  # Entry point. Parses CLI arguments, validates paths and flags, sets a
  # collection of global state (normalized_heights, user_window_ext, window
  # extension deltas, and the shared accumulator lists processDielectrics /
  # PatternShapes), then delegates to TranslateUniversalFile() to do the
  # actual conversion work.

  syntax = "python3 Universal2FasterCap.py <Universal_format_pattern_folder> <FasterCap_format_output_folder> <heights_reference>(normalized|standard) <2D/3D> ?-sim_window_ext_3D <lower_dx> <lower_dz> <lower_dy> <upper_dx> <upper_dz> <upper_dy> ?-sim_window_ext_2D <lower_dx> <lower_dy> <upper_dx> <upper_dy>"

  argvlength = len(argv)

  ## check if a file path has been specified ##
  # 3D -> 5 or 12
  # 2D -> 5 or 10
  # NOTE: due to operator precedence, "argvlength != 12 or argvlength != 11"
  # is always True for any argvlength (it can't simultaneously equal both
  # 12 and 11), so this condition effectively reduces to
  if (argvlength != 5) and (argvlength != 12 or argvlength != 11):
    print("ERROR! Wrong number of arguments!")
    print("Re-run with: " + syntax)
    sys.exit(-2)

  ## check specified Raphael Format file path exists ##
  if not (os.path.exists(argv[1])):
    print("ERROR! Specified Universal Pattern File path does not exist!")
    print("Re-run with: " + syntax)
    sys.exit(-2)

  ## check specified FasterCap output folder path exists ##
  if not (os.path.exists(argv[2])):
    os.makedirs(argv[2])
    print(f"Folder '{argv[2]}' created successfully.")

  
  global normalized_heights
  ## check if heights are normalized or standard in reference to ground planes ##
  if (argv[3] == "normalized"):
    print("Heights are assumed normalized based on the lowest Ground Plane!")
    normalized_heights = True
  elif (argv[3] == "standard"):
    print("Heights have their standard values")
    normalized_heights = False
  else:
    print("ERROR! Uknown specified heights_reference value!")
    print("Re-run with: " + syntax)
    sys.exit(-2)
  
  if (argv[4] == "3D"):
    print("3D Geometries")
    mode = 1
  elif (argv[4] == "2D"):
    print("2D Geometries")
    mode = 2
  else:
    print("ERROR! Uknown type of geometry!")
    print("Re-run with: " + syntax)
    sys.exit(-2)


  global window_min_x_ext
  global window_min_z_ext
  global window_min_y_ext
  global window_max_x_ext
  global window_max_z_ext
  global window_max_y_ext
  global user_window_ext

  ## check if simulation window extension is provided ##
  if argvlength != 5:
    if not argv[5] == "-sim_window_ext":
      print(f"ERROR! Invalid argument {argv[5]}!")
      print("Re-run with: " + syntax)
      sys.exit(-2)
    else:
      # parse the appropriate number of extension values depending on mode
      # (3D: x/z/y lower+upper = 6 values; 2D: x/y lower+upper = 4 values)
      try:
        if (mode == 1):
          window_min_x_ext = float(argv[6])
          window_min_z_ext = float(argv[7])
          window_min_y_ext = float(argv[8])
          window_max_x_ext = float(argv[9])
          window_max_z_ext = float(argv[10])
          window_max_y_ext = float(argv[11])
          user_window_ext = True
        elif (mode == 2):
          window_min_x_ext = float(argv[6])
          window_min_y_ext = float(argv[7])
          window_max_x_ext = float(argv[8])
          window_max_y_ext = float(argv[9])
          user_window_ext = True
      except ValueError: 
        print("ERROR! Simulation Window Extension parameters must be numbers!")
        print("Re-run with: " + syntax)
        sys.exit(-2)
  else:
    # no CLI-supplied extension -> default to zero on all sides; per-file
    # SIM_WIN_EXT records in the universal-format file will be used instead
    # (see TranslateUniversalFile's user_window_ext == False branches)
    window_min_x_ext = 0.0
    window_min_z_ext = 0.0
    window_min_y_ext = 0.0
    window_max_x_ext = 0.0
    window_max_z_ext = 0.0
    window_max_y_ext = 0.0
    user_window_ext = False
    
  global processDielectrics
  global PatternShapes

  global patternswindowwidth
  global patternswindowthickness
  global patternswindowheight
  global currentpath

  global total_ground_planes

  currentpath = os.getcwd()
  
  patternswindowwidth = 0.0
  patternswindowthickness = 0.0
  patternswindowheight = 0.0

  processDielectrics = []
  PatternShapes = []

  TranslateUniversalFile(argv[1], argv[2], mode)
if (__name__ == "__main__"):
  main(sys.argv[0:])