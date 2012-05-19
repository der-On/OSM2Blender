import bpy
import math
from collections import OrderedDict
import mathutils
from mathutils import geometry
from mathutils import Vector
from io_osm.import_osm import *
from io_osm.osm_rules import *

AEROWAY_TAG = 'aeroway' # TODO: add way support
UNIT_SCALES = {'m':1,'ft':0.305}
LAYERS = ['building','barrier','object','area','road']

ROADS_SORT_ORDER = [None,'cycleway','railway']

EQUATOR_RADIUS = 6378137.0      # greatest earth radius (equator)
POLE_RADIUS = 6356752.314245    # smallest earth radius (pole)

class OSM():
  xml = None
  nodes = {}
  ways = {}
  relations = {}
  bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
  geo_bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
  dimensions = Vector((0.0,0.0))
  version = ''
  generator = ''
  process = 0.0
  process_step = 0.0
  ground = None
  camera = None
  offset = 0.0
  scene = None
  temp_scene = None
  rules = None
  tags = {}

  # config
  right_hand_traffic = True
  offset_step = 0.01
  file = None

  def __init__(self,xml):
    self.nodes = {}
    self.ways = {}
    self.relations = {}
    self.bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
    self.geo_bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
    self.dimensions = Vector((0.0,0.0))
    self.version = ''
    self.generator = ''
    self.process = 0.0
    self.process_step = 0.0
    self.ground = None
    self.camera = None
    self.offset = 0.0
    self.scene = bpy.context.scene
    self.temp_scene = None

    self.setConfig()
    self.setRules()

    self.xml = xml
    self.version = xml.attributes['version'].value
    self.generator = xml.attributes['generator'].value
    _bounds = xml.getElementsByTagName('bounds').item(0)

    latLon = (float(_bounds.attributes['minlat'].value),float(_bounds.attributes['minlon'].value))
    co = self.getCoordinates(latLon,False)
    self.bounds[0][0] = co[0]
    self.bounds[0][1] = co[1]
    self.geo_bounds[0][0] = latLon[0]
    self.geo_bounds[0][1] = latLon[1]

    latLon = (float(_bounds.attributes['maxlat'].value),float(_bounds.attributes['maxlon'].value))
    co = self.getCoordinates(latLon,False)
    self.bounds[1][0] = co[0]
    self.bounds[1][1] = co[1]
    self.geo_bounds[1][0] = latLon[0]
    self.geo_bounds[1][1] = latLon[1]

    self.dimensions[0] = self.bounds[1][0]-self.bounds[0][0]
    self.dimensions[1] = self.bounds[1][1]-self.bounds[0][1]

  def setConfig(self):
    osm = self.scene.osm_settings
    if osm.traffic_direction == 'right':
      self.right_hand_traffic = True
    else:
      self.right_hand_traffic = False

    self.offset_step = osm.offset_step
    self.file = osm.file

  def setRules(self):
    osm = self.scene.osm_settings
    if osm.rules!='' and osm.rules in bpy.data.texts:
      self.rules = Rules.fromString(bpy.data.texts[osm.rules].as_string())

  def generate(self,rebuild):
    self.scene = bpy.context.scene

    osm = self.scene.osm_settings
    # append geobounds to scene
    osm.geo_bounds_lat[0] = self.geo_bounds[0][0]
    osm.geo_bounds_lat[1] = self.geo_bounds[1][0]
    osm.geo_bounds_lon[0] = self.geo_bounds[0][1]
    osm.geo_bounds_lon[1] = self.geo_bounds[1][1]

    # create temporary scene
    #        self.temp_scene = bpy.data.scenes.new("OSM_import")
    #bpy.context.scene.background_set = self.temp_scene

    self.nodes = self.getNodes(self.xml)
    self.ways = self.getWays(self.xml)

    deselectObjects(self.scene)

    #self.createGround()
    #self.createCamera()

    if rebuild:
      self.process_step = 100/len(self.scene.objects)
      self.createFromExisting()
    else:
      self.process_step = 100/(len(self.ways)+len(self.nodes))
      # generate all node objects
      self.createObjects(rebuild)

      # generate all ways
      self.createWays(rebuild)

    # self.sortAreas()
    # self.sortTrafficways()

    # set to layers
    if rebuild==False:
      for i in range(0,len(LAYERS)):
        if LAYERS[i]:
          if LAYERS[i]=='object':
            self.setToLayer(self.nodes,i,True)
          elif LAYERS[i] in self.ways:
            self.setToLayer(self.ways[LAYERS[i]],i)

      self.linkObjects(self.nodes)
      self.linkObjects(self.ways)
      updateScene(self.scene)

      if debug:
        debugger.debug("OSM import complete!")
    else:
      updateScene(self.scene)
      if debug:
        debugger.debug('OSM rebuild complete!')

  def linkObjects(self,dict):
    for id in dict:
      if (dict[id].object): self.scene.objects.link(dict[id].object)

  def createFromExisting(self):
    for object in self.scene.objects:
      osm = object.osm_data
      if osm.id!='':
        # check if it is an object
        if osm.id in self.nodes:
          self.nodes[osm.id].generate(True,object)
          if debug:
            debugger.debug('%3.2f' % (self.process) +'% ' + self.nodes[osm.id].name)
        elif osm.id in self.ways:
          self.ways[osm.id].generate(True,object)
          if debug:
            debugger.debug('%3.2f' % (self.process) +'% ' + self.ways[osm.id].name)
      self.process+=self.process_step

  def setToLayer(self,items,layer,dict = False):
    layers = self.getLayers()
    layers[layer] = True
    for item in items:
      if dict:
        if items[item].object:
          items[item].object.layers = layers
      elif item.object:
        item.object.layers = layers

  def getLayers(self):
    return [False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False]

  def createWays(self,rebuild):
    if debug:
      debugger.debug('\nCreating ways ...')
    for id in self.ways:
      way = self.ways[id]
      way.generate(rebuild)
      if debug and way.object:
        debugger.debug('%3.2f' % (self.process) +'% ' + way.name)
      self.process+=self.process_step

  def createObjects(self,rebuild):
    if debug:
      debugger.debug('\nCreating objects ...')
    for id in self.nodes:
      node = self.nodes[id]
      node.generate(rebuild)
      if debug and node.object:
        debugger.debug('%3.2f' % (self.process) +'% ' + node.name)
      self.process+=self.process_step

  def sortAreas(self):
    pass
    """
    if debug:
      debugger.debug('\nZ-sorting areas ...' )

    way_offset = 0.0
    max_offset = self.offset
    for way in self.ways['area']:
      if way.object:
        way_offset = self.sortCollidingWaysByAreaSize(way)
        if max_offset<way_offset:
          max_offset = way_offset

    self.offset = max_offset
  """

  def sortTrafficways(self):
    pass
    """
    if debug:
      debugger.debug('\nZ-sorting trafficways ...' )

    max_offset = self.offset+self.offset_step
    for way in self.ways['trafficway']:
      if way.object:
        way.setOffset(self.getTrafficwayOffset(way))

    self.offset = max_offset
    """

  def getTrafficwayOffset(self,way):
    colliding = self.getCollidingWays(way,'offset')
    if len(colliding)>0:
      offset = colliding[0].offset
      sort_index = way.preset.osm_preset.trafficway_sort
      return offset+(self.offset_step*(sort_index+1))
    return 0.0

  def createGround(self):
    mesh = bpy.data.meshes.new("Ground")
    self.ground = bpy.data.objects.new("Ground",mesh)
    self.scene.objects.link(self.ground)

    setOnLayer(self.ground,0)

    mesh.vertices.add(4)
    mesh.vertices[0].co = Vector((0.0,0.0,0.0))
    mesh.vertices[1].co = Vector((self.dimensions[0],0.0,0.0))
    mesh.vertices[2].co = Vector((self.dimensions[0],self.dimensions[1],0.0))
    mesh.vertices[3].co = Vector((0.0,self.dimensions[1],0.0))

    mesh.faces.add(1)
    mesh.faces[0].vertices = [0,1,2,3]

    mesh.edges.add(4)
    for i in range(0,4):
      ii = i*2
      mesh.edges[i].vertices[0] = ii % 4
      mesh.edges[i].vertices[0] = (ii+1) % 4

    mesh.validate()

    # create uvs
    uv_texture = mesh.uv_textures.new()
    scale = self.area_texture_scale
    uv_face = uv_texture.data[0]
    mesh_face = mesh.faces[0]
    v1 = mesh.vertices[mesh_face.vertices[0]].co.copy()*scale
    v2 = mesh.vertices[mesh_face.vertices[1]].co.copy()*scale
    v3 = mesh.vertices[mesh_face.vertices[2]].co.copy()*scale
    v4 = mesh.vertices[mesh_face.vertices[3]].co.copy()*scale
    uv_face.uv_raw = (v1[0],v1[1],v2[0],v2[1],v3[0],v3[1],v4[0],v4[1])

    self.ground.location[2] = -self.offset_step

    # Material
    selectObject(self.ground,self.scene)
    bpy.ops.object.material_slot_add()
    if 'ground' in bpy.data.materials:
      self.ground.material_slots[0].material = bpy.data.materials["ground"]

    deselectObject(self.ground)

  def createCamera(self):
    angle = 60.0;
    cam = bpy.data.cameras.new("OSMCamera")
    self.camera = bpy.data.objects.new("OSMCamera",cam)
    self.scene.objects.link(self.camera)

    setOnLayer(self.camera,0)

    self.camera.rotation_euler = Vector((math.radians(angle),0.0,0.0))
    self.camera.data.type = 'ORTHO'
    self.camera.data.clip_end = 40000.0 # 40 km
    self.camera.data.clip_start = 0.0
    self.camera.data.lens_unit = 'DEGREES'
    self.camera.data.lens = 90
    self.camera.data.ortho_scale = self.dimensions[0]
    self.camera.location = Vector((self.dimensions[0]/2,self.dimensions[1]/(2+(90/angle)),100))

    #self.scene.camera = self.camera

  def getNodes(self,xml):
    if debug:
      debugger.debug("parsing nodes ...")

    nodes = {}
    xml_nodes = xml.getElementsByTagName('node')
    for i in range(0,xml_nodes.length):
      node = Node(xml_nodes.item(i),self)
      nodes[node.id] = node

    return nodes

  def getWays(self,xml):
    ways = {}
    if debug:
      debugger.debug("parsing ways ...")

    xml_ways = xml.getElementsByTagName('way')
    for i in range(0,xml_ways.length):
      way = Way(xml_ways.item(i),self)
      ways[way.id] = way

    return ways

  def getNodeRefs(self,way,xml):
    refs = []
    xml_nds = xml.getElementsByTagName('nd')
    for i in range(0,xml_nds.length):
      id = xml_nds.item(i).attributes['ref'].value
      if id in self.nodes:
        node = self.nodes[id]
        node.ways.append(way)
        refs.append(node)

    return refs

  def getTags(self,xml):
    tags = {}
    xml_tags = xml.getElementsByTagName('tag')
    for i in range(0,xml_tags.length):
      tag = Tag(xml_tags.item(i),self)
      tags[tag.name] = tag

    return tags


  # Python implementation for mercator projection by Paulo Silva taken from: http://wiki.openstreetmap.org/wiki/Mercator

  def mercX(self,lon):
    return EQUATOR_RADIUS*math.radians(lon)

  def mercY(self,lat):
    if lat>89.5:lat=89.5
    if lat<-89.5:lat=-89.5
    r_major=EQUATOR_RADIUS
    r_minor=POLE_RADIUS
    temp=r_minor/r_major
    eccent=math.sqrt(1-temp**2)
    phi=math.radians(lat)
    sinphi=math.sin(phi)
    con=eccent*sinphi
    com=eccent/2
    con=((1.0-con)/(1.0+con))**com
    ts=math.tan((math.pi/2-phi)/2)/con
    y=0-r_major*math.log(ts)
    return y

  # Returns x/y coordinates of a given latitude, longitude and elevation using the sperical mercator projection.
  def getCoordinates(self,latLonEle,use_bounds = True):
    from math import sqrt, cos, sin, radians

    if len(latLonEle)==3:
      co = Vector((0.0,0.0,0.0))
    else:
      co = Vector((0.0,0.0))

    #        rf = POLE_RADIUS/EQUATOR_RADIUS
    #
    #        r = (EQUATOR_RADIUS*POLE_RADIUS)/sqrt((POLE_RADIUS*cos(latLonEle[0]))**2 + (EQUATOR_RADIUS*sin(latLonEle[0]))**2)
    #        co[1] = (r/180)*latLonEle[0]*self.latlon_scale
    #        co[0] = ((r/2)/180)*latLonEle[1]*self.latlon_scale

    co[0] = self.mercX(latLonEle[1])
    co[1] = self.mercY(latLonEle[0])

    if len(latLonEle)==3:
      co[2] = latLonEle[2]
    if use_bounds:
      co[0]-=self.bounds[0][0]
      co[1]-=self.bounds[0][1]

    return co

  def getMeters(self,value):
    parts = value.partition(' ')
    if len(parts)>1:
      size = float(parts[0])
      unit = parts[1]
      if unit in UNIT_SCALES:
        size=size*UNIT_SCALES[unit]
    else:
      size = float(parts[0])

    return size

  def sortCollidingWaysByAreaSize(self,way):
    way_offset = self.offset
    if way.id not in self.ways['sorted']:
      colliding = self.getCollidingWays(way,way.type)
      if len(colliding)>0:
        for i in range(0,len(colliding)):
          way_offset = self.offset + (i*self.offset_step)
          colliding[i].setOffset(way_offset)

          # mark as sorted so it wont be sorted again
          self.ways['sorted'].append(colliding[i].id)

    return way_offset

  def getCollidingWays(self,way,type,sort_by='area',reverse=True):
    from operator import attrgetter
    colliding = []
    if way.type and way.type==type:
      colliding.append(way)

    if type in self.ways:
      for c_way in self.ways[type]:
        if c_way.object and hasattr(c_way.object,'data') and c_way.object.osm_data.id!='' and c_way!=way:
          if self.waysCollide(way,c_way):
            colliding.append(c_way)

    colliding.sort(key=attrgetter(sort_by),reverse=reverse)
    return colliding

  def waysCollide(self,way_a,way_b):
    # pre check with bounding box in 2d plane
    collide = (way_a.bounds[0][0] < way_b.bounds[1][0]) and (way_a.bounds[1][0] > way_b.bounds[0][0]) and (way_a.bounds[0][1] < way_b.bounds[1][1]) and (way_a.bounds[1][1] > way_b.bounds[0][1])
    if collide: # detail check with point to face intersection in 2d plane
      # TODO: we should use nodes instead of mesh vertices
      mesh_a = way_a.object.data
      mesh_b = way_b.object.data
      for i in range(0,len(way_b.object.data.faces)):
        for ii in range(0,len(way_a.object.data.vertices)):
          face = mesh_b.faces[i]
          va = mesh_a.vertices[ii].co.copy()
          va = Vector((va[0],va[1]))
          if len(face.vertices)>3:
            vb_1 = mesh_b.vertices[face.vertices[0]].co.copy()
            vb_2 = mesh_b.vertices[face.vertices[1]].co.copy()
            vb_3 = mesh_b.vertices[face.vertices[2]].co.copy()
            vb_4 = mesh_b.vertices[face.vertices[3]].co.copy()

            vb_1 = Vector((vb_1[0],vb_1[1]))
            vb_2 = Vector((vb_2[0],vb_2[1]))
            vb_3 = Vector((vb_3[0],vb_3[1]))
            vb_4 = Vector((vb_4[0],vb_4[1]))

            if geometry.intersect_point_quad_2d(va,vb_1,vb_2,vb_3,vb_4):
              return True
          else:
            vb_1 = mesh_b.vertices[face.vertices[0]].co.copy()
            vb_2 = mesh_b.vertices[face.vertices[1]].co.copy()
            vb_3 = mesh_b.vertices[face.vertices[2]].co.copy()

            vb_1 = Vector((vb_1[0],vb_1[1]))
            vb_2 = Vector((vb_2[0],vb_2[1]))
            vb_3 = Vector((vb_3[0],vb_3[1]))

            if geometry.intersect_point_tri_2d(va,vb_1,vb_2,vb_3):
              return True
      return False
    else:
      return False

  def setLayer(self,way):
    for i in range(0,len(LAYERS)):
      if way.type==LAYERS[i]:
        way.object.layers[i] = True
      else:
        way.object.layers[i] = False

    if LAYERS[0]!=way.type:
      way.object.layers[0] = False


class Tag():
  name = None
  value = None
  osm = None

  def __init__(self,xml,osm):
    self.osm = osm
    self.name = xml.attributes['k'].value
    self.value = xml.attributes['v'].value

"""
class TagConfig():
    name = None
    value = None
    presets = []
    groups = []

    def  __init__(self,name,value):
        self.name = name
        self.value = value
        self.presets = []
        self.groups = []

    def orderPresets(self):
        self.presets.sort(cmp=self.orderByPriority())

    def orderGroups(self):
        self.groups.sort(cmp=self.orderByPriority())
        
    def orderByPriority(a,b):
        if self.getTagInList(a.osm_preset.tags).priority > self.getTagInList(b.osm_preset.tags).priority:
            return 1
        else:
            return -1

    def getTagInList(self,list):
        for tag in list:
            if tag.name==self.name and tag.value==self.value:
                return tag
        return None        
"""

class Way():
  id = None
  name = "Way"
  nodes = []
  tags = {}
  type = None
  object = None
  outline = None
  geometries = []
  osm = None
  area = 0.0
  bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
  offset = 0.0
  level = 0
  rules = []
  rulePresets = []

  def __init__(self,xml,osm):
    self.osm = osm
    self.id = xml.attributes['id'].value
    self.tags = self.osm.getTags(xml)
    self.nodes = self.osm.getNodeRefs(self,xml)
    self.area = 0.0
    self.bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
    self.offset = 0.0
    self.level = 0
    self.rules = []
    self.rulePresets = []
    self.geometries = []
    self.setRules()
    self.setLevel()
    self.setName()

  def setLevel(self):
    if 'level' in self.tags:
      try:
        self.level = char(int(self.tags['level'].value))
      except:
        self.level = -1

  def setName(self):
    if 'name' in self.tags:
      self.name = self.tags['name'].value
    else:
      self.name = '%s_%s' % (self.type,self.id)

  def generate(self,rebuild, object = None):
    if self.level>=0:
      self.createObject(rebuild,object)
      if self.object:
        # create outline
        self.outline = Outline(self)
        self.outline.generate(rebuild)

        self.createGeometries(rebuild)
        for geometry in self.geometries:
          geometry.generate(rebuild)

        self.area = self.outline.getArea()
        self.bounds = self.outline.getBounds()

        # align objects along center edge
        self.alignObjects()

  def createGeometries(self,rebuild = False):
    # TODO: look for USAGE_TAGS groups and place them on top of building, on every node for lines or in object center for areas
    # TODO: allow for scalable or repeatable groups in between nodes for lines (cables of powerlines for example)
    # TODO: allow for scatterable groups for natural area types (trees, bushes, etc.)

    i = 0
    for rule in self.rules:
      if 'type' in rule.settings:
        type = rule.settings['type'].value
        preset = self.getRulePreset(i)
        geometry = None
        if type == 'building':
          geometry = Building(self,rule,preset)
        elif type == 'trafficway':
          geometry = Trafficway(self,rule,preset)
        elif type == 'area':
          geometry = Area(self,rule,preset)
        elif type == 'barrier':
          geometry = Barrier(self,rule,preset)

        if geometry:
          self.geometries.append(geometry)
      i+=1

  def createObject(self,rebuild, object = None):
    if rebuild==False:
      mesh = bpy.data.meshes.new(self.name)
      self.object = bpy.data.objects.new(self.name,mesh)

      # add imported osm data and tags to object
      osm = self.object.osm_data
      osm.id = self.id
      osm.name = self.name
      for tag in self.tags:
        obj_tag = osm.tags.add()
        obj_tag.name = self.tags[tag].name
        obj_tag.value = self.tags[tag].value

      #self.osm.scene.objects.link(self.object)
      self.object.location = self.getCenter()
    elif object:
      self.object = object

  def getCenter(self):
    v = Vector((0.0,0.0,0.0))
    for node in self.nodes:
      v+=node.co
    return v/len(self.nodes)

  def alignObjects(self):
    from mathutils import Euler
    upvector = Vector((0.0,0.0,1.0))

    for i in range(0,len(self.nodes)):
      # check for referenced objects and align them with center edge on xy plane, means rotate on z-axis only
      if self.nodes[i].object:
        normal = self.outline.normals[i]
        rot = normal.to_track_quat('X','Z').to_euler()
        self.nodes[i].object.rotation_euler = rot

        """
        # offset the object to the side so it's next to a road
        if self.type=='trafficway' and self.outline.width>0:
          offset = normal*(self.outline.width/2)
          if self.osm.right_hand_traffic:
            self.nodes[i].object.location = self.nodes[i].co-offset
          else:
            self.nodes[i].object.location = self.nodes[i].co+offset
        """

  def setRules(self):
    # get all matching rules
    for obj_name in self.osm.rules.rules_by_selector:
      rules = self.osm.rules.rules_by_selector[obj_name]
      for rule in rules:
        if rule.matchesData(self):
          self.rules.append(rule)

          if obj_name in bpy.data.objects:
            preset = bpy.data.objects[obj_name]
          else:
            preset = None
          self.rulePresets.append(preset)

  def getRule(self,index = 0):
    if index < len(self.rules):
      return self.rules[index]
    else:
      return None

  def getRulePreset(self,index = 0):
    if index < len(self.rulePresets):
      return self.rulePresets[index]
    else:
      return None

  def setOffset(self,offset):
    if self.object:
      self.offset = offset
      self.object.location[2] = offset

  def isClockwise(self):
    pos = 0
    neg = 0
    num = len(self.nodes)-1

    for i in range(0,num):
      v1 = Vector((self.nodes[(i-1) % num].co[0],self.nodes[(i-1) % num].co[1]))
      v2 = Vector((self.nodes[i].co[0],self.nodes[i].co[1]))
      v3 = Vector((self.nodes[(i+1) % num].co[0],self.nodes[(i+1) % num].co[1]))

      cross = (v2[0]-v1[0])*(v3[1]-v2[1]) - (v2[1]-v1[1])*(v3[0]-v2[0])

      if cross>0:
        pos+=1
      if cross<0:
        neg+=1

    return neg>=pos

  def isClosed(self):
    num = len(self.nodes)
    for i in range(0,3):
      if self.nodes[0].co[i]!=self.nodes[num-1].co[i]:
        return False
    return True


class Geometry():
  way = None
  normals = []
  rule = None
  preset = None
  generator = None

  def __init__(self,way,rule = None,preset = None):
    self.way = way
    self.normals = []
    self.rule = rule
    self.preset = preset
    self.generator = None
    self.setNormals()

  def setNormals(self):
    for i in range(0,len(self.way.nodes)):
      self.normals.append(self.getNodeNormal(i))

  def generate(self,rebuild):
      pass

  def getArea(self):
    area = 0.0
    if hasattr(self.way.object.data,'faces'):
      for face in self.way.object.data.faces:
        area+=face.area
    return area

  def getBounds(self):
    x_max = 0.0
    y_max = 0.0
    x_min = 0.0
    y_min = 0.0

    for v in self.way.object.data.vertices:
      if v.co[0]<x_min: x_min = v.co[0]
      if v.co[0]>x_max: x_max = v.co[0]
      if v.co[1]<y_min: y_min = v.co[1]
      if v.co[1]>y_max: y_max = v.co[1]

    x_min-=self.way.object.location[0]/2
    x_max-=self.way.object.location[0]/2
    y_min-=self.way.object.location[1]/2
    y_max-=self.way.object.location[1]/2

    return ((x_min,y_min),(x_max,y_max))

  def getNodeNormal(self,i):
    upvector = Vector((0.0,0.0,1.0))
    closed = self.way.isClosed()

    if closed:
      num = len(self.way.nodes)-1
    else:
      num = len(self.way.nodes)

    if i>0:
      start_v = self.way.nodes[i-1].co
    else:
      if closed:
        start_v = self.way.nodes[num-1].co
      else:
        start_v = self.way.nodes[i].co

    if i<num-1:
      end_v = self.way.nodes[i+1].co
    else:
      if closed:
        end_v = self.way.nodes[0].co
      else:
        end_v = self.way.nodes[i].co

    return (start_v-end_v).normalized().cross(upvector)


class Outline(Geometry):
  def __init__(self,way,rule = None,preset = None):
    super(Outline,self).__init__(way,rule,preset)

  def generate(self,rebuild):
    super(Outline,self).generate(rebuild)

    #material = self.way.getMaterial()

    # closed outlines might need direction switch
    closed =  self.way.isClosed()
    if closed:
      clockwise = self.way.isClockwise()
      if clockwise:
        self.way.nodes.reverse()

    num = len(self.way.nodes)-1 # first and last are at the same location, so we do not need the last node
    mesh = self.way.object.data

    if rebuild==False:
      mesh.vertices.add(num)
      mesh.edges.add(num)

      for i in range(0,num):
        mesh.vertices[i].co = self.way.nodes[i].co.copy()-self.way.object.location

        if closed==False:
          if i<num-1:
            mesh.edges[i].vertices = [i,(i+1)]
        else:
          mesh.edges[i].vertices = [i,(i+1) % num]

      mesh.validate()


class Building(Geometry):
  height = None
  levels = 0
  default_levels = 3

  def __init__(self,way,rule,preset):
    super(Building,self).__init__(way,rule,preset)
    self.levels = None
    self.height = None
    self.setHeight()

  def setHeight(self):
    if 'height' in self.way.tags:
      self.height = self.way.osm.getMeters(self.way.tags['height'].value)
      self.levels = self.height/self.preset.dimensions[2]
    else:
      self.levels = self.default_levels
      if 'building_default_levels' in self.rule.settings:
        self.levels = int(self.rule.settings['building_default_levels'])
      self.height = self.levels*self.preset.dimensions[2]

  def generate(self,rebuild):
    super(Building,self).generate(rebuild)

    if 'building_part' in self.rule.settings:
      part = self.rule.settings['building_part'].value

      if part == 'facade':
        self.createFacade(rebuild)
      elif part == 'roof':
        roof_type = 'flat_roof'
        if 'roof_type' in self.rule.settings:
          roof_type = self.rule.settings['roof_type']
        if roof_type == 'flat':
          self.createFlatRoof(rebuild)
        elif roof_type=='sloped':
          self.createSlopedRoof(rebuild)

  def createFacade(self,rebuild):
    self.generator = LinearArrayGenerator(self.preset,self.way)
    self.generator.generate(rebuild)

  def createFlatRoof(self,rebuild):
    pass
    """
    self.generator = GeometryGenerator(self.preset,self.way)
    preset = self.way.getPreset(1)
    mesh = self.way.object.data
    num = len(self.way.nodes)-1

    from mathutils import geometry

    if rebuild==False:
      # roof
      veclist = []
      for i in range(num,num*2):
        veclist.append(mesh.vertices[i].co)

      fill_vecs = geometry.tesselate_polygon([veclist])

      # add new edges and faces
      mesh.faces.add(len(fill_vecs))
      mesh.edges.add(len(fill_vecs)*3)
      for i in range(0,len(fill_vecs)):
        v1 = fill_vecs[i][0]+num
        v2 = fill_vecs[i][1]+num
        v3 = fill_vecs[i][2]+num
        mesh.faces[i+num].vertices = [v3,v2,v1]
        mesh.faces[i+num].use_smooth = True
        mesh.faces[i+num].material_index = 1 # roof material
        mesh.edges[i+(num*3)].vertices = [v1,v2]
        mesh.edges[i+(num*3)+1].vertices = [v2,v3]
        mesh.edges[i+(num*3)+2].vertices = [v3,v1]

      mesh.validate()

    # roof uvs
    uv_texture = mesh.uv_textures[0]

    # get roof angle
    roof_normal = Vector((0.0,0.0,0.0))
    for i in range(0,num):
      roof_normal+=self.normals[i]
    roof_normal = roof_normal/num
    rot = roof_normal.to_track_quat('X','Z').to_euler()

    for i in range(num,len(mesh.faces)):
      uv_face = uv_texture.data[i]
      mesh_face = mesh.faces[i]

      v1 = mesh.vertices[mesh_face.vertices[0]].co.copy()
      v2 = mesh.vertices[mesh_face.vertices[1]].co.copy()
      v3 = mesh.vertices[mesh_face.vertices[2]].co.copy()
      if len(mesh_face.vertices)==4:
        v4 = mesh.vertices[mesh_face.vertices[3]].co.copy()
      else:
        v4 = Vector((0.0,0.0,0.0))

      v1.rotate(rot)
      v2.rotate(rot)
      v3.rotate(rot)
      v4.rotate(rot)

      uv_face.uv_raw = (v1[0],v1[1],v2[0],v2[1],v3[0],v3[1],v4[0],v4[1])
  """

  def createSlopedRoof(self,rebuild):
    pass
    """
    self.createFlatRoof(rebuild)
    num = len(self.way.nodes)-1

    mesh = self.way.object.data

    # select roof faces
    roof_faces = []
    for i in range(num,len(mesh.faces)):
      roof_faces.append(mesh.faces[i])

    preset = self.way.getPreset(1)
    height = preset.osm_preset.dimensions[2]

    self.do_inset(mesh, roof_faces, 100, height*10, True, True)

    # roof uvs
    uv_texture = mesh.uv_textures[0]

    # get roof angle
    roof_normal = Vector((0.0,0.0,0.0))
    for i in range(0,num):
      roof_normal+=self.normals[i]
    roof_normal = roof_normal/num
    rot = roof_normal.to_track_quat('X','Z').to_euler()

    for i in range(num,len(mesh.faces)):
      uv_face = uv_texture.data[i]
      mesh_face = mesh.faces[i]

      v1 = mesh.vertices[mesh_face.vertices[0]].co.copy()
      v2 = mesh.vertices[mesh_face.vertices[1]].co.copy()
      v3 = mesh.vertices[mesh_face.vertices[2]].co.copy()
      if len(mesh_face.vertices)==4:
        v4 = mesh.vertices[mesh_face.vertices[3]].co.copy()
      else:
        v4 = Vector((0.0,0.0,0.0))

      #rot = mesh_face.normal.copy().to_track_quat('Y','X').to_euler()

      v1.rotate(rot)
      v2.rotate(rot)
      v3.rotate(rot)
      v4.rotate(rot)

      uv_face.uv_raw = (v1[0],v1[1],v2[0],v2[1],v3[0],v3[1],v4[0],v4[1])
  """
  """
  def do_inset(self, mesh, faces, amount, height, region, as_percent):
    from mesh_inset import geom
    from mesh_inset import model
    from mesh_inset import offset
    from mesh_inset import triquad

    if amount <= 0.0:
      return
    pitch = math.atan(height / amount)
    selfaces = []
    selface_indices = []
    for face in faces:
      selfaces.append(face)
      selface_indices.append(face.index)
    m = geom.Model()
    # if add all mesh.vertices, coord indices will line up
    # Note: not using Points.AddPoint which does dup elim
    # because then would have to map vertices in and out
    m.points.pos = [v.co.to_tuple() for v in mesh.vertices]
    for f in selfaces:
      m.faces.append(list(f.vertices))
      m.face_data.append(f.index)
    orig_numv = len(m.points.pos)
    orig_numf = len(m.faces)
    model.BevelSelectionInModel(m, amount, pitch, True, region, as_percent)
    if len(m.faces) == orig_numf:
      # something went wrong with Bevel - just treat as no-op
      return
      # blender_faces: newfaces but all 4-tuples and no 0
    # in 4th position if a 4-sided poly
    blender_faces = []
    blender_old_face_index = []
    for i in range(orig_numf, len(m.faces)):
      f = m.faces[i]
      if len(f) == 3:
        blender_faces.append(list(f) + [0])
        blender_old_face_index.append(m.face_data[i])
      elif len(f) == 4:
        if f[3] == 0:
          blender_faces.append([f[3], f[0], f[1], f[2]])
        else:
          blender_faces.append(f)
        blender_old_face_index.append(m.face_data[i])
    num_new_vertices = len(m.points.pos) - orig_numv
    mesh.vertices.add(num_new_vertices)
    for i in range(orig_numv, len(m.points.pos)):
      mesh.vertices[i].co = mathutils.Vector(m.points.pos[i])
    start_faces = len(mesh.faces)
    mesh.faces.add(len(blender_faces))
    for i, newf in enumerate(blender_faces):
      mesh.faces[start_faces + i].vertices_raw = newf
      # copy face attributes from old face that it was derived from
      bfi = blender_old_face_index[i]
      if bfi and 0 <= bfi < start_faces:
        bfacenew = mesh.faces[start_faces + i]
        bface = mesh.faces[bfi]
        bfacenew.material_index = bface.material_index
        bfacenew.use_smooth = bface.use_smooth
    mesh.update(calc_edges=True)
    #TODO: remove original faces
"""

class Trafficway(Geometry):
  width = 0.0
  lanes = 1

  def __init__(self,way,rule,preset):
    super(Trafficway,self).__init__(way,rule,preset)
    self.lanes = 1
    self.width = 0
    self.setWidth()

  def setWidth(self):
    if 'lanes' in self.way.tags:
      self.lanes = int(self.way.tags['lanes'].value)
    self.width = self.preset.dimensions[1]

  def generate(self,rebuild):
    super(Trafficway,self).generate(rebuild)
    self.generator = LinearArrayGenerator(self.preset,self.way)
    self.generator.generate(rebuild)
    """
    from mathutils import Euler

    num = len(self.way.nodes)
    v_num = len(self.way.nodes)*2

    mesh = self.way.object.data

    if rebuild==False:
      mesh.vertices.add(v_num)
      mesh.faces.add(num-1)
      mesh.edges.add(num+num+num-2)

    #        prev_normal = None

    for i in range(0,num):
      width = self.width

      # If an endpoint is shared with other ways we have to align it and create width transitions
      if i==0 or i==num-1 and len(self.way.nodes[i].ways)>1:
        node = self.way.nodes[i]
        node_normal = self.normals[i]
        normal = node_normal.copy()
        num_shared = 1

        for shared_way in self.way.nodes[i].ways:
          if shared_way!=self.way and shared_way.type==self.way.type: # only use shared nodes from other trafficways
            shared_index = node.getIndexInWay(shared_way)

            # found an endpoint
            if shared_index==0 or shared_index==len(shared_way.nodes)-1: # only use endpoints
              shared_normal = shared_way.geometry.normals[shared_index]
              # ignore hard turns
              angle = node_normal.angle(shared_normal)
              if abs(math.degrees(angle))<=80:
                normal+=shared_normal
                num_shared+=1
                # create a transition to the widest trafficway
                if width<shared_way.geometry.width:
                  width = shared_way.geometry.width
            else: # some point in between, so its a junction
              # create transition to thiner trafficway
              if width>shared_way.geometry.width:
                width = shared_way.geometry.width

        normal = normal/num_shared
      else:
        normal = self.normals[i]

      # TODO: on 90° turns or more we have to switch normal direction, maybe keep last normal and check if we switched from <0 to >0?

      # be sure to make the z-axis of the normal 0
      normal[2] = 0

      offset = normal*(width/2)

      # position vertices
      ii = i*2

      mesh.vertices[ii].co = self.way.nodes[i].co+offset-self.way.object.location # left
      mesh.vertices[ii+1].co = self.way.nodes[i].co-offset-self.way.object.location # right

      # joining edge
      if rebuild==False:
        mesh.edges[i].vertices = [ii,ii+1]

        if i<num-1: # ignore last node, as it has no side edges
          # left edge
          mesh.edges[i+num].vertices = [ii,ii+2]
          # right edge
          mesh.edges[i+(num*2)-1].vertices = [ii+1,ii+3]

          # face
          mesh.faces[i].vertices_raw = [ii,ii+1,ii+3,ii+2]
          mesh.faces[i].use_smooth = True

        #            prev_normal = normal

    if rebuild==False:
      mesh.validate()

    # create uvs
    if rebuild:
      uv_texture = mesh.uv_textures[0]
    else:
      uv_texture = mesh.uv_textures.new()

    uv_y = 0.0

    if preset and preset.osm_preset.base_type=='trafficway':
      texture_lanes = preset.osm_preset.lanes
    else:
      texture_lanes = 2

    # uv height factors
    width = self.lanes/texture_lanes
    hf = 1/(self.width/self.lanes)

    for i in range(0,len(uv_texture.data)):
      uv_face = uv_texture.data[i]
      mesh_face = mesh.faces[i]

      face_length = self.getNodeDistance(self.way.nodes[i],self.way.nodes[i+1])
      height = hf*face_length

      # set uvs
      uv_face.uv_raw = (0.0,uv_y,width,uv_y,width,uv_y+height,0.0,uv_y+height)

      uv_y+=height

  def getNodeDistance(self,node_a,node_b):
    return (node_a.co-node_b.co).magnitude
"""

class Area(Geometry):
  def __init__(self,way,rule,preset):
    super(Area,self).__init__(way,rule,preset)

  def generate(self,rebuild):
    super(Area,self).generate(rebuild)

    preset = self.way.getPreset()

    num = len(self.way.nodes)-1 # first and last are at the same location, so we do not need the last node
    mesh = self.way.object.data

    if rebuild==False:
      mesh.vertices.add(num)
      mesh.edges.add(num)

      for i in range(0,num):
        mesh.vertices[i].co = self.way.nodes[i].co.copy()-self.way.object.location
        mesh.edges[i].vertices = [i,(i+1) % num]

      # fill
      veclist = []
      for i in range(0,num):
        veclist.append(mesh.vertices[i].co)

      fill_vecs = geometry.tesselate_polygon([veclist])

      # add new edges and faces
      mesh.faces.add(len(fill_vecs))
      mesh.edges.add(len(fill_vecs)*3)
      for i in range(0,len(fill_vecs)):
        v1 = fill_vecs[i][0]
        v2 = fill_vecs[i][1]
        v3 = fill_vecs[i][2]
        mesh.faces[i].vertices = [v3,v2,v1]
        mesh.faces[i].use_smooth = True
        mesh.edges[i].vertices = [v1,v2]
        mesh.edges[i+1].vertices = [v2,v3]
        if len(mesh.edges)>=i+2:
          mesh.edges[i+2].vertices = [v3,v1]

      mesh.validate()

      # create uvs
      uv_texture = mesh.uv_textures.new()
    else:
      uv_texture = mesh.uv_textures[0]

    for i in range(0,len(mesh.faces)):
      uv_face = uv_texture.data[i]
      mesh_face = mesh.faces[i]
      v1 = mesh.vertices[mesh_face.vertices[0]].co.copy()
      v2 = mesh.vertices[mesh_face.vertices[1]].co.copy()
      if len(mesh_face.vertices)>=3:
        v3 = mesh.vertices[mesh_face.vertices[2]].co.copy()
      else:
        v3 = (0.0,0.0)
      if len(mesh_face.vertices)==4:
        v4 = mesh.vertices[mesh_face.vertices[3]].co.copy()
      else:
        v4 = (0.0,0.0)

      uv_face.uv_raw = (v1[0],v1[1],v2[0],v2[1],v3[0],v3[1],v4[0],v4[1])


class Barrier(Geometry):
  height = None
  width = 0.0

  def __init__(self,way,rule,preset):
    super(Barrier,self).__init__(way,rule,preset)
    self.height = None
    self.width = 0.0

    # set width
    self.width = preset.dimensions[1]

  def generate(self,rebuild):
    super(Barrier,self).generate(rebuild)


class Node():
  id = None
  lat = 0.0
  lon = 0.0
  ele = 0.0
  co = Vector((0.0,0.0,0.0))
  tags = {}
  type = None
  osm = None
  object = None
  name = None
  level = 0
  ways = []

  def __init__(self,xml,osm):
    self.osm = osm
    self.id = xml.attributes['id'].value
    self.lat = float(xml.attributes['lat'].value)
    self.lon = float(xml.attributes['lon'].value)
    self.object = None
    self.name = None
    self.level = 0
    self.ways = []

    if 'ele' in xml.attributes:
      self.ele = float(xml.attributes['ele'].value)

    self.co = self.osm.getCoordinates((self.lat,self.lon,self.ele))
    self.tags = self.osm.getTags(xml)
    self.setLevel()

  def setLevel(self):
    if 'level' in self.tags:
      try:
        self.level = char(int(self.tags['level'].value))
      except:
        self.level = -1

  def setName(self):
    if self.type:
      if 'name' in self.tags:
        self.name = self.tags['name'].value
      else:
        self.name = self.type+'_'+self.id

  def generate(self,rebuild, object = None):
    if len(self.tags)>0 and self.level>=0:
      self.type = 'object'
      self.setName()
      self.createObject(rebuild,object)
      if self.object:
        self.create(rebuild)

  def createObject(self,rebuild, object):
    if rebuild==False:
      self.object = bpy.data.objects.new(self.name,None)
      osm = self.object.osm_data
      osm.id = self.id
      osm.name = self.name
      for tag in self.tags:
        obj_tag = osm.tags.add()
        obj_tag.name = self.tags[tag].name
        obj_tag.value = self.tags[tag].value

        #self.osm.scene.objects.link(self.object)
    elif object:
      self.object = object

  def create(self,rebuild):
    self.object.location = self.co
    """
    group = None
    priority = -1

    for name in self.tags:
      tag = self.tags[name]
      tag_configs = self.osm.getTagConfig(tag.name,tag.value)
      if len(tag_configs)>0:
        for tag_config in tag_configs:
          for tag_group in tag_config.groups:
            group_tag = tag_config.getTagInList(tag_group.osm.tags)
            tag_priority = group_tag.priority

            if tag_priority>=priority:
              # check if we have mandatory tags
              mandatory = getMandatoryTags(tag_group)
              found = 0
              for i in range(0,len(mandatory)):
                if mandatory[i].name in self.tags:
                  if mandatory[i].value=='' or self.tags[mandatory[i].name].value==mandatory[i].value:
                    found+=1

              if found==len(mandatory):
                group = tag_group
                priority = tag_priority

    if group:
      self.object.dupli_type = 'GROUP'
      self.object.dupli_group = group
    """

  def getIndexInWay(self,way):
    from operator import indexOf
    return indexOf(way.nodes,self)


class GeometryGenerator():

  def __init__(self,preset,way):
    self.way = way
    self.preset = preset
    self.parts = []
    self.track_axis = 'X'
    self.up_axis = 'Z'

  def generate(self,rebuild = False):
    pass


class LinearArrayGenerator(GeometryGenerator):

  def __init__(self,preset,way):
    super(LinearArrayGenerator,self).__init__(preset,way)

  def generate(self,rebuild = False):
    super(LinearArrayGenerator,self).generate(rebuild)

    counter = 1

    last_co = None
    last_part = None

    for point in self.way.object.data.vertices:
      if last_co == None or (last_co[0]!=point.co[0] or last_co[1]!=point.co[1] or last_co[2]!=point.co[2]):
        # create object
        part_copy = bpy.data.objects.new('part_%d' % counter,self.preset.data)

        # parent part_copy to outline
        part_copy.parent = self.way.object

        # position object
        part_copy.location[0] = point.co[0]
        part_copy.location[1] = point.co[1]
        part_copy.location[2] = point.co[2]

        # append to list
        self.parts.append(part_copy)

        # link to scene
        bpy.context.scene.objects.link(part_copy)

        if last_part!=None:
          # align last part object along z-axis
          self.alignPart(last_part,part_copy)
          # add array modifier
          self.repeatPart(last_part,part_copy)

        # increase counter and store last position and object
        counter+=1
        last_co = point.co
        last_part = part_copy

    # align last part to first again
    # scene needs update, otherwhise alignment will look wrong
    self.alignPart(last_part,self.parts[0])
    self.repeatPart(last_part,self.parts[0])
    bpy.context.scene.update()
    # update part mesh so booleans work correctly
    last_part.data.update()


  def alignPart(self,part,next_part):
    v_to = mathutils.Vector(next_part.location)
    v_from = mathutils.Vector(part.location)
    v = v_to - v_from
    rot = v.to_track_quat('X','Z')
    part.rotation_euler = rot.to_euler()

  def createBoolObject(self,name,part,length):
    add_size = 0.1

    # create box with dimensions matchin one part tile
    bool_mesh = bpy.data.meshes.new(part.name+'_x_bool')
    bool_mesh.vertices.add(8)
    bool_mesh.edges.add(12)
    bool_mesh.polygons.add(6)

    # align lower vertices (clockwise)
    bool_mesh.vertices[0].co = [0.0,(-1.0*part.dimensions[1])-add_size,0.0-add_size]
    bool_mesh.vertices[1].co = [(1.0*length)+add_size,(-1.0*part.dimensions[1])-add_size,0.0-add_size]
    bool_mesh.vertices[2].co = [(1.0*length)+add_size,(1.0*part.dimensions[1])+add_size,0.0-add_size]
    bool_mesh.vertices[3].co = [0.0,(1.0*part.dimensions[1])+add_size,0.0-add_size]

    # align upper vertices
    bool_mesh.vertices[4].co = [0.0,(-1.0*part.dimensions[1])-add_size,(1.0*part.dimensions[2])+add_size]
    bool_mesh.vertices[5].co = [(1.0*length)+add_size,(-1.0*part.dimensions[1])-add_size,(1.0*part.dimensions[2])+add_size]
    bool_mesh.vertices[6].co = [(1.0*length)+add_size,(1.0*part.dimensions[1])+add_size,(1.0*part.dimensions[2])+add_size]
    bool_mesh.vertices[7].co = [0.0,(1.0*part.dimensions[1])+add_size,(1.0*part.dimensions[2])+add_size]

    # create loops
    bool_mesh.loops.add(24)
    bool_mesh.loops.foreach_set("vertex_index", (0,1,2,3,4,5,6,7,0,4,7,3,1,5,6,2,0,1,5,4,3,2,6,7))

    # create polygons
    # bool_mesh.polygons[0].vertices = [0,1,2,3] # bottom
    bool_mesh.polygons[0].loop_start = 0
    bool_mesh.polygons[0].loop_total = 4
    # bool_mesh.polygons[1].vertices = [4,5,6,7] # top
    bool_mesh.polygons[1].loop_start = 4
    bool_mesh.polygons[1].loop_total = 4
    # bool_mesh.polygons[2].vertices = [0,4,7,3] # left
    bool_mesh.polygons[2].loop_start = 8
    bool_mesh.polygons[2].loop_total = 4
    # bool_mesh.polygons[3].vertices = [1,5,6,2] # right
    bool_mesh.polygons[3].loop_start = 12
    bool_mesh.polygons[3].loop_total = 4
    # bool_mesh.polygons[4].vertices = [0,1,5,4] # back
    bool_mesh.polygons[4].loop_start = 16
    bool_mesh.polygons[4].loop_total = 4
    # bool_mesh.polygons[5].vertices = [3,2,6,7] # front
    bool_mesh.polygons[5].loop_start = 20
    bool_mesh.polygons[5].loop_total = 4
    bool_mesh.validate()
    bool_mesh.update(calc_edges=True)

    bool_obj = bpy.data.objects.new(part.name+'_x_bool',bool_mesh)

    bpy.context.scene.objects.link(bool_obj)

    selectObject(bpy.context.scene,bool_obj)
    selectMesh()
    bpy.ops.mesh.normals_make_consistent()
    deselectMesh()
    deselectObjects(bpy.context.scene)

    return bool_obj


  def repeatPart(self,part,next_part):
    v_to = mathutils.Vector(next_part.location)
    v_from = mathutils.Vector(part.location)
    v = v_to - v_from
    need_length = v.length
    length = part.dimensions[0]

    if need_length > length:
      need_count = math.ceil(need_length/length)
      array = part.modifiers.new('part_x_repeat','ARRAY')
      array.count = need_count
      array.fit_type = 'FIXED_COUNT'
      array.relative_offset_displace = [1.0,0.0,0.0]
      array.use_relative_offset = True

      bool_obj = self.createBoolObject(part.name+'_x_bool',part,(length*need_count)-need_length)

      # parent bool_obj to part
      bool_obj.parent = part

      bool_obj.location[0] = need_length
      bool_obj.hide_render = True
      bool_obj.hide = True

      bool = part.modifiers.new('part_x_repeat_cut','BOOLEAN')
      bool.operation = 'UNION'
      bool.object = bool_obj # this causes a segfault
