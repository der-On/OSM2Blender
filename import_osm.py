import bpy
from mathutils import Vector
from xml.dom.minidom import parse,parseString
from .helpers import Debugger,Profiler

BUILDING_TAG = 'building'
STREET_TAG = 'highway'
AREA_TAGS = ('area','natural','landuse','leisure')
RAILWAY_TAG = 'railway'
LANE_WIDTH = 3
DEFAULT_BUILDING_HEIGHT = 10
UNIT_SCALES = {'m':1,'ft':0.305}

EQUATOR_RADIUS = 6378137        # greatest earth radius (equator)
POLE_RADIUS = 6356752.314245    # smallest earth radius (pole)
LATLON_SCALE = 3.33

profile = True
debug = True
log = False

profiler = Profiler()
debugger = Debugger()

def load_osm(filepath, context):
    if debug:
        debugger.start(log)
    if profile:
        profiler.start("load_osm")
    if debug:
        debugger.debug("OSM import started: %r..." % filepath)
        debugger.debug("parsing xml to dom ...")

    if profile:
        profiler.start('xml.parse')

    xml = parse(filepath)

    if profile:
        profiler.end('xml.parse')

    root = xml.documentElement
    osm = OSM(root)
    osm.generate()
    xml.unlink()

    if profile:
        profiler.end('load_osm')
        if debug:
            debugger.debug("\nProfiling results:")
            debugger.debug(profiler.getTimes())

def load(operator, context, filepath=""):
    load_osm(filepath, context)
    return {'FINISHED'}

def selectObject(obj):
    if profile:
        profiler.start('selectObject')

    obj.select = True
    bpy.context.scene.objects.active = obj #set the mesh object to current

    if profile:
        profiler.end('selectObject')

def selectMesh():
    if profile:
        profiler.start('selectMesh')

    if bpy.context.scene.objects.active:
        bpy.ops.object.mode_set(mode='EDIT') #Operators
        bpy.ops.mesh.select_all(action='SELECT')#select all the face/vertex/edge

    if profile:
        profiler.end('selectMesh')

def deselectMesh():
    if profile:
        profiler.start('deselectMesh')

    bpy.ops.object.mode_set(mode='OBJECT') # set it in object

    if profile:
        profiler.end('deselectMesh')

def deselectObjects():
    if profile:
        profiler.start('deselectObjects')

    for i in bpy.context.scene.objects: i.select = False #deselect all objects

    if profile:
        profiler.end('deselectObjects')

def deselectObject(obj):
    if profile:
        profiler.start('deselectObject')

    obj.select = False

    if profile:
        profiler.end('deselectObject')

def update():
    if profile:
        profiler.start('update')

    bpy.context.scene.update()

    if profile:
        profiler.end('update')

def getMeters(value):
    if profile:
        profiler.start('getMeters')

    parts = value.partition(' ')
    if len(parts)>1:
        size = float(parts[0])
        unit = parts[1]
        if unit in UNIT_SCALES:
            size=size*UNIT_SCALES[unit]
    else:
        size = float(parts[0])

    if profile:
        profiler.end('getMeters')

    return size

class OSM():
    xml = None
    nodes = {}
    ways = {}
    relations = {}
    bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
    version = ''
    generator = ''
    generate_process = 0.0

    def __init__(self,xml):
        self.xml = xml
        self.version = xml.attributes['version'].value
        self.generator = xml.attributes['generator'].value
        _bounds = xml.getElementsByTagName('bounds').item(0)

        latLon = (float(_bounds.attributes['minlat'].value),float(_bounds.attributes['minlon'].value))
        co = self.getCoordinates(latLon,False)
        self.bounds[0][0] = co[0]
        self.bounds[0][1] = co[1]

        latLon = (float(_bounds.attributes['maxlat'].value),float(_bounds.attributes['maxlon'].value))
        co = self.getCoordinates(latLon,False)
        self.bounds[1][0] = co[0]
        self.bounds[1][1] = co[1]

    def generate(self):
        if profile:
            profiler.start('OSM.generate')

        self.nodes = self.getNodes(self.xml)
        self.ways = self.getWays(self.xml)

        deselectObjects()

        process_step = 100/len(self.ways)
        
        for id in self.ways:
            self.ways[id].generate()
            self.generate_process+=process_step

        update()

        if debug:
            debugger.debug("OSM import complete!")
        if profile:
            profiler.end('OSM.generate')

    def getNodes(self,xml):
        if profile:
            profiler.start('OSM.getNodes')
        if debug:
            debugger.debug("parsing nodes ...")

        nodes = {}
        xml_nodes = xml.getElementsByTagName('node')
        for i in range(0,xml_nodes.length):
            node = Node(xml_nodes.item(i),self)
            nodes[node.id] = node

        if profile:
            profiler.end('OSM.getNodes')

        return nodes

    def getWays(self,xml):
        if profile:
            profiler.start('OSM.getWays')
        if debug:
            debugger.debug("parsing ways ...")

        ways = {}
        xml_ways = xml.getElementsByTagName('way')
        for i in range(0,xml_ways.length):
            way = Way(xml_ways.item(i),self)
            ways[way.id] = way

        if profile:
            profiler.end('OSM.getWays')

        return ways

    def getNodeRefs(self,xml):
        if profile:
            profiler.start('OSM.getNodeRefs')
            
        refs = []
        xml_nds = xml.getElementsByTagName('nd')
        for i in range(0,xml_nds.length):
            id = xml_nds.item(i).attributes['ref'].value
            if id in self.nodes:
                node = self.nodes[id]
                refs.append(node)

        if profile:
            profiler.end('OSM.getNodeRefs')

        return refs

    def getTags(self,xml):
        if profile:
            profiler.start('OSM.getTags')

        tags = {}
        xml_tags = xml.getElementsByTagName('tag')
        for i in range(0,xml_tags.length):
            tag = Tag(xml_tags.item(i),self)
            tags[tag.name] = tag

        if profile:
            profiler.end('OSM.getTags')

        return tags

    def getCoordinates(self,latLonEle,use_bounds = True):
        if profile:
            profiler.start('OSM.getCoordinates')

        from math import sqrt, cos, sin
        
        if len(latLonEle)==3:
            co = Vector((0.0,0.0,0.0))
        else:
            co = Vector((0.0,0.0))

        rf = POLE_RADIUS/EQUATOR_RADIUS

        r = (EQUATOR_RADIUS*POLE_RADIUS)/sqrt((POLE_RADIUS*cos(latLonEle[0]))**2 + (EQUATOR_RADIUS*sin(latLonEle[0]))**2)
        co[1] = (r/180)*latLonEle[0]*LATLON_SCALE
        co[0] = ((r/2)/180)*latLonEle[1]*LATLON_SCALE
        
        if len(latLonEle)==3:
            co[2] = latLonEle[2]
        if use_bounds:
            co[0]-=self.bounds[0][0]
            co[1]-=self.bounds[0][1]

        if profile:
            profiler.end('OSM.getCoordinates')

        return co

class Tag():
    name = None
    value = None
    osm = None

    def __init__(self,xml,osm):
        self.osm = osm
        self.name = xml.attributes['k'].value
        self.value = xml.attributes['v'].value


class Way():
    id = None
    name = "Way"
    nodes = []
    tags = {}
    type = None
    height = 0
    width = 0
    object = None
    osm = None

    def __init__(self,xml,osm):
        self.osm = osm
        self.id = xml.attributes['id'].value
        self.tags = self.osm.getTags(xml)
        self.nodes = self.osm.getNodeRefs(xml)
        self.setType()
        self.setName()

    def setType(self):
        if profile:
            profiler.start('Way.setType')

        self.type = [None,None,None]
        if BUILDING_TAG in self.tags:
            self.type[0] = 'building'
            self.type[1] = self.tags[BUILDING_TAG].value
            if 'height' in self.tags:
                self.height = getMeters(self.tags['height'].value)
            else:
                self.height = DEFAULT_BUILDING_HEIGHT

        for name in AREA_TAGS:
            if name in self.tags:
                self.type[0] = 'area'
                if self.tags[name].value!='yes':
                    self.type[1] = name
                    self.type[2] = self.tags[name].value
        
        if STREET_TAG in self.tags:
            self.type[0] = 'street'
            self.type[1] = self.tags[STREET_TAG].value
            if 'lanes' in self.tags:
                self.width = LANE_WIDTH*float(self.tags['lanes'].value)

        if profile:
            profiler.end('Way.setType')
    
    def setName(self):
        if profile:
            profiler.start('Way.setName')
            
        if 'name' in self.tags:
            self.name = self.tags['name'].value
        else:
            self.name = '%s_%s' % (self.type[0],self.id)

        if profile:
            profiler.end('Way.setName')

    def generate(self):
        if profile:
            profiler.start('Way.generate')
            
        if self.type[0]:
            if debug:
                debugger.debug('%3.2f' % (self.osm.generate_process) +'% ' + self.name)
            self.createObject()
            selectObject(self.object)
            self.setMaterial()
            self.create()
            deselectObject(self.object)

        if profile:
            profiler.end('Way.generate')

    def create(self):
        if profile:
            profiler.start('Way.create')
            
        if self.type[0]=='building':
            self.createBuilding()
        elif self.type[0]=='area':
            self.createArea()
        elif self.type[0]=='street':
            self.createStreet()

        if profile:
            profiler.end('Way.create')

    def createObject(self):
        if profile:
            profiler.start('Way.createObject')

        mesh = bpy.data.meshes.new(self.name)
        self.object = bpy.data.objects.new(self.name,mesh)
        bpy.context.scene.objects.link(self.object)

        if profile:
            profiler.end('Way.createObject')

    def createEdges(self):
        if profile:
            profiler.start('Way.createEdges')

        # add egdes
        mesh = self.object.data
        mesh.vertices.add(len(self.nodes))
        for i in range(0,len(self.nodes)):
            mesh.vertices[i].co = self.nodes[i].co

        mesh.edges.add(len(mesh.vertices))
        for i in range(0,len(mesh.edges)):
            mesh.edges[i].vertices[0] = i
            if i<len(mesh.vertices)-1:
                mesh.edges[i].vertices[1] = i+1
            else:
                mesh.edges[i].vertices[1] = i

        if profile:
            profiler.end('Way.createEdges')

    def createBuilding(self):
        if profile:
            profiler.start('Way.createBuilding')

        self.createEdges()
        selectMesh()

        if profile:
            profiler.start('mesh.fill')
        bpy.ops.mesh.fill()
        if profile:
            profiler.end('mesh.fill')

        if profile:
            profiler.start('mesh.extrude')
        bpy.ops.mesh.extrude_region_move()
        bpy.ops.transform.transform(value=[0.0,0.0,self.height,0.0])
        if profile:
            profiler.end('mesh.extrude')

        if profile:
            profiler.start('remove_doubles')
        bpy.ops.mesh.remove_doubles()
        if profile:
            profiler.end('remove_doubles')
            
        if profile:
            profiler.start('mesh.normals')
        bpy.ops.mesh.normals_make_consistent()
        if profile:
            profiler.end('mesh.normals')
            
        deselectMesh()
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        if profile:
            profiler.end('Way.createBuilding')

    def createArea(self):
        if profile:
            profiler.start('Way.createArea')

        self.createEdges()
        selectMesh()
        
        if profile:
            profiler.start('mesh.fill')
        bpy.ops.mesh.fill()
        if profile:
            profiler.end('mesh.fill')

        if profile:
            profiler.start('remove_doubles')
        bpy.ops.mesh.remove_doubles()
        if profile:
            profiler.end('remove_doubles')

        if profile:
            profiler.start('mesh.normals')
        bpy.ops.mesh.normals_make_consistent()
        if profile:
            profiler.end('mesh.normals')
            
        deselectMesh()
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        if profile:
            profiler.end('Way.createArea')

    def createStreet(self):
        if profile:
            profiler.start('Way.createStreet')

        self.createEdges()
        selectMesh()
        # TODO: extrude edges to left and right by self.width/2
            
        if profile:
            profiler.start('mesh.normals')
        bpy.ops.mesh.normals_make_consistent()
        if profile:
            profiler.end('mesh.normals')
            
        deselectMesh()
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        if profile:
            profiler.end('Way.createStreet')

    def setMaterial(self):
        if profile:
            profiler.start('Way.setMaterial')
            
        bpy.ops.object.material_slot_add()
        if self.type[2] and bpy.data.materials.get(self.type[2]):
            self.object.material_slots[0].material = bpy.data.materials[self.type[2]]
        elif self.type[1] and bpy.data.materials.get(self.type[1]):
            self.object.material_slots[0].material = bpy.data.materials[self.type[1]]
        elif self.type[0] and bpy.data.materials.get(self.type[0]):
            self.object.material_slots[0].material = bpy.data.materials[self.type[0]]

        if profile:
            profiler.end('Way.setMaterial')


class Node():
    id = None
    lat = 0.0
    lon = 0.0
    ele = 0.0
    co = Vector((0.0,0.0,0.0))
    tags = {}
    osm = None

    def __init__(self,xml,osm):
        self.osm = osm
        self.id = xml.attributes['id'].value
        self.lat = float(xml.attributes['lat'].value)
        self.lon = float(xml.attributes['lon'].value)

        if 'ele' in xml.attributes:
            self.ele = float(xml.attributes['ele'].value)

        self.co = self.osm.getCoordinates((self.lat,self.lon,self.ele))
        self.tags = self.osm.getTags(xml)