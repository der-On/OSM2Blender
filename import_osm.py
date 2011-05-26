import bpy
import math
from mathutils import geometry
from mathutils import Vector
from xml.dom.minidom import parse,parseString
from .helpers import Debugger,Profiler

BUILDING_TAG = 'building'
STREET_TAG = 'highway'
AREA_TAGS = ('area','natural','landuse','leisure')
RAILWAY_TAG = 'railway'
LANE_WIDTH = 3.5
DEFAULT_BUILDING_HEIGHT = 15
UNIT_SCALES = {'m':1,'ft':0.305}
OFFSET_STEP = 0.01
OFFSET_ORDER = ['natural','landuse','leisure','street','railway','land','sand','beach','grassland','grass','coastline','water']
LAYERS = ['building','area','street',None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None]

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

def setOnLayer(obj,layer):
    for i in range(0,20):
        if i == layer:
            obj.layers[i] = True
        else:
            obj.layers[i] = False

def editMode(mode=True):
    if mode:
        if bpy.context.scene.objects.active:
            bpy.ops.object.mode_set(mode='EDIT') #Operators
    else:
        if bpy.context.scene.objects.active:
            bpy.ops.object.mode_set(mode='OBJECT') #Operators

def selectMesh():
    if profile:
        profiler.start('selectMesh')

    if bpy.context.scene.objects.active:
        bpy.ops.object.mode_set(mode='EDIT') #Operators
        bpy.ops.mesh.select_all(action='SELECT')#select all the face/vertex/edge

    if profile:
        profiler.end('selectMesh')

def selectCurve():
    if profile:
        profiler.start('selectCurve')

    if bpy.context.scene.objects.active:
        bpy.ops.object.mode_set(mode='EDIT') #Operators
        bpy.ops.curve.select_all(action='SELECT')#select all the face/vertex/edge

    if profile:
        profiler.end('selectCurve')

def deselectCurve():
    deselectMesh()

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
    dimensions = Vector((0.0,0.0))
    version = ''
    generator = ''
    generate_process = 0.0
    ground = None
    camera = None
    sub_offsets = {}

    def __init__(self,xml):
        self.nodes = {}
        self.ways = {}
        self.relations = {}
        self.bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
        self.dimensions = Vector((0.0,0.0))
        self.version = ''
        self.generator = ''
        self.generate_process = 0.0
        self.ground = None
        self.camera = None
        self.sub_offsets = {}

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

        self.dimensions[0] = self.bounds[1][0]-self.bounds[0][0]
        self.dimensions[1] = self.bounds[1][1]-self.bounds[0][1]

    def generate(self):
        if profile:
            profiler.start('OSM.generate')

        self.nodes = self.getNodes(self.xml)
        self.ways = self.getWays(self.xml)

        deselectObjects()

        self.createGround()
        self.createCamera()

        process_step = 100/len(self.ways)
        
        for id in self.ways:
            self.ways[id].generate()
            if self.ways[id].object:
                self.setOffset(self.ways[id])
                self.setLayer(self.ways[id])
            self.generate_process+=process_step

        update()

        if debug:
            debugger.debug("OSM import complete!")
        if profile:
            profiler.end('OSM.generate')

    def createGround(self):
        mesh = bpy.data.meshes.new("Ground")
        self.ground = bpy.data.objects.new("Ground",mesh)
        bpy.context.scene.objects.link(self.ground)

        setOnLayer(self.ground,0)

        mesh.vertices.add(4)
        mesh.vertices[0].co = Vector((0.0,0.0,0.0))
        mesh.vertices[1].co = Vector((self.dimensions[0],0.0,0.0))
        mesh.vertices[2].co = Vector((self.dimensions[0],self.dimensions[1],0.0))
        mesh.vertices[3].co = Vector((0.0,self.dimensions[1],0.0))
        
        selectObject(self.ground)
        selectMesh()
        
        bpy.ops.mesh.edge_face_add()
        bpy.ops.uv.unwrap()

        deselectMesh()

        # Material
        bpy.ops.object.material_slot_add()
        if 'ground' in bpy.data.materials:
            self.ground.material_slots[0].material = bpy.data.materials["ground"]

        deselectObject(self.ground)

    def createCamera(self):
        angle = 60.0;
        cam = bpy.data.cameras.new("OSMCamera")
        self.camera = bpy.data.objects.new("OSMCamera",cam)
        bpy.context.scene.objects.link(self.camera)

        setOnLayer(self.camera,0)

        self.camera.rotation_euler = Vector((math.radians(angle),0.0,0.0))
        self.camera.data.type = 'ORTHO'
        self.camera.data.clip_end = 40000.0 # 40 km
        self.camera.data.clip_start = 0.0
        self.camera.data.lens_unit = 'DEGREES'
        self.camera.data.lens = 90
        self.camera.data.ortho_scale = self.dimensions[0]
        self.camera.location = Vector((self.dimensions[0]/2,self.dimensions[1]/(2+(90/angle)),100))

        bpy.context.scene.camera = self.camera

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

    def setOffset(self,way):
        for i in range(0,len(OFFSET_ORDER)):
            if OFFSET_ORDER[i]==way.type[0] or OFFSET_ORDER[i]==way.type[1] or OFFSET_ORDER[i]==way.type[2]:
                way.object.location[2] = OFFSET_STEP*(i+1)
                return

    def setLayer(self,way):
        for i in range(0,20):
            if way.type[0]==LAYERS[i]:
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
            else:
                self.width = LANE_WIDTH

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
            self.create()
            self.setMaterial()
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

        self.object.data.use_auto_smooth = True
        #self.object.data.show_double_sided = False
        bpy.ops.object.shade_smooth()

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

        selectMesh()

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

#        selectMesh()
#
#        if profile:
#            profiler.start('mesh.unwrap')
#        bpy.ops.uv.unwrap()
#        if profile:
#            profiler.end('mesh.unwrap')

        deselectMesh()
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        if profile:
            profiler.end('Way.createArea')

    def createStreet(self):
        if profile:
            profiler.start('Way.createStreet')

        self.createEdges()
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        bpy.ops.object.convert(target="CURVE")

        # uv mapping
        bpy.ops.object.data.use_uv_as_generated = True

        #self.object.rotation_euler[1] = math.radians(90)
#        selectCurve()
#        bpy.ops.transform.create_orientation(use=True)
#        bpy.ops.transform.rotate(value=[math.radians(-90)],axis=(0.0,1.0,0.0))
#
#        bpy.ops.curve.subdivide()
#
#        deselectCurve()

        self.object.data.extrude = 0.00001

        bpy.ops.object.modifier_add(type="SOLIDIFY")
        solidify = self.object.modifiers[0]
        solidify.thickness = self.width
        solidify.offset = 0
        
        bpy.ops.object.convert(target="MESH")

        selectMesh()
#        bpy.ops.mesh.subdivide(smoothness=1)
#        deselectMesh()
        
        if profile:
            profiler.start('remove_doubles')
        bpy.ops.mesh.remove_doubles()
        if profile:
            profiler.end('remove_doubles')

        if profile:
            profiler.start('mesh.normals')
        bpy.ops.mesh.normals_make_consistent(inside=True)
        if profile:
            profiler.end('mesh.normals')

        deselectMesh()

        if profile:
            profiler.end('Way.createStreet')
        
    def setMaterial(self):
        if profile:
            profiler.start('Way.setMaterial')
            
        bpy.ops.object.material_slot_add()
        if self.type[2] and (self.type[2] in bpy.data.materials):
            self.object.material_slots[0].material = bpy.data.materials[self.type[2]]
        elif self.type[1] and (self.type[1] in bpy.data.materials):
            self.object.material_slots[0].material = bpy.data.materials[self.type[1]]
        elif self.type[0] and (self.type[0] in bpy.data.materials):
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