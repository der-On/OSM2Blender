import bpy
import math
from mathutils import geometry
from mathutils import Vector
from xml.dom.minidom import parse,parseString
from io_osm.helpers import Debugger

# TODO: support levels and multilevels.

AEROWAY_TAG = 'aeroway' # TODO: add way support
BUILDING_TAG = 'building'
BARRIER_TAG = 'barrier'
USAGE_TAGS = ['amenity','shop','office','craft','emergency','tourism','historic','military']
ROAD_TAG = 'highway'
CYCLEWAY_TAG = 'cycleway'
AREA_TAGS = ('area','natural','landuse','leisure')
RAILWAY_TAG = 'railway'
LANE_WIDTH = 3.0
CYCLEWAY_WIDTH = 1.0
RAILWAY_WIDTH = 1.5
DEFAULT_BUILDING_HEIGHT = 15
UNIT_SCALES = {'m':1,'ft':0.305}
OFFSET_STEP = 0.001
LAYERS = ['buildings','areas','roads','objects',None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None]

ROADS_SORT_ORDER = [None,'cycleway','railway']

EQUATOR_RADIUS = 6378137        # greatest earth radius (equator)
POLE_RADIUS = 6356752.314245    # smallest earth radius (pole)
LATLON_SCALE = 3.33

RIGHT_HAND_TRAFFIC = True

profiler = True
debug = True
log = False

debugger = Debugger()

def load_osm(filepath, context):
    if debug:
        debugger.start(log)
    if debug:
        debugger.debug("OSM import started: %r..." % filepath)
        debugger.debug("parsing xml to dom ...")

    # deactive undo for better performance and less memory usage
    global_undo = context.user_preferences.edit.use_global_undo
    context.user_preferences.edit.use_global_undo = False

    xml = parse(filepath)

    root = xml.documentElement
    osm = OSM(root)
    if profiler:
        import profile
        import time
        profile.runctx('osm.generate()',{'debug':debug,'debugger':debugger,'log':log},{'osm':osm},'profile_results_'+time.strftime("%y-%m-%d-%H-%M-%S"))
    else:
        osm.generate()
        
    xml.unlink()

    # reset undo preference
    context.user_preferences.edit.use_global_undo = global_undo

def load(operator, context, filepath=""):
    load_osm(filepath, context)
    return {'FINISHED'}

def selectObject(obj,scene):
    obj.select = True
    scene.objects.active = obj #set the mesh object to current

def setOnLayer(obj,layer):
    for i in range(0,20):
        if i == layer:
            obj.layers[i] = True
        else:
            obj.layers[i] = False

def editMode(scene,mode=True):
    if mode:
        if scene.objects.active:
            bpy.ops.object.mode_set(mode='EDIT') #Operators
    else:
        if scene.objects.active:
            bpy.ops.object.mode_set(mode='OBJECT') #Operators

def selectMesh(mode=True):
    bpy.ops.object.mode_set(mode='EDIT') #Operators
    if mode:
        action = 'SELECT'
    else:
        action = 'DESELECT'
    bpy.ops.mesh.select_all(action=action)#select all the face/vertex/edge

def selectCurve():
    bpy.ops.object.mode_set(mode='EDIT') #Operators
    bpy.ops.curve.select_all(action='SELECT')#select all the face/vertex/edge

def deselectCurve():
    deselectMesh()

def deselectMesh():
    bpy.ops.object.mode_set(mode='OBJECT') # set it in object

def deselectObjects(scene):
    for i in scene.objects: i.select = False #deselect all objects

def deselectObject(obj):
    obj.select = False

def update(scene):
    scene.update()

def getMeters(value):
    parts = value.partition(' ')
    if len(parts)>1:
        size = float(parts[0])
        unit = parts[1]
        if unit in UNIT_SCALES:
            size=size*UNIT_SCALES[unit]
    else:
        size = float(parts[0])

    return size

class OSM():
    xml = None
    nodes = {}
    ways = {'area':[],'building':[],'road':[],'by_id':{},'sorted':[]}
    relations = {}
    bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
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

    def __init__(self,xml):
        self.nodes = {}
        self.ways = {'area':[],'building':[],'road':[],'by_id':{},'sorted':[]}
        self.relations = {}
        self.bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
        self.dimensions = Vector((0.0,0.0))
        self.version = ''
        self.generator = ''
        self.process = 0.0
        self.process_step = 0.0
        self.ground = None
        self.camera = None
        self.offset = 0.0
        self.scene = None
        self.temp_scene = None

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
        self.scene = bpy.context.scene

        # create temporary scene
#        self.temp_scene = bpy.data.scenes.new("OSM_import")
        #bpy.context.scene.background_set = self.temp_scene

        self.nodes = self.getNodes(self.xml)
        self.ways = self.getWays(self.xml)

        deselectObjects(self.scene)
        
        self.createGround()
        self.createCamera()
        
        self.process_step = 100/len(self.ways['by_id'])
        
        # generate all node objects
        self.createObjects()

        # generate all ways
        self.createWays()

        self.sortAreas()
        self.sortRoads()
        
        # move ways back to main scene
#        for id in self.ways['by_id']:
#            way = self.ways['by_id'][id]
#            if way.object:
#                self.scene.objects.link(way.object)

#        bpy.data.scenes.remove(self.temp_scene)


        # set to layers
        for i in range(0,20):
            if LAYERS[i]:
                if LAYERS[i]=='objects':
                    self.setToLayer(self.nodes,i,True)
                elif LAYERS[i] in self.ways:
                    self.setToLayer(self.ways[LAYERS[i]],i)

        update(self.scene)

        if debug:
            debugger.debug("OSM import complete!")

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

    def createWays(self):
        for id in self.ways['by_id']:
            way = self.ways['by_id'][id]
            way.generate()
#            if way.object:
#                self.setLayer(way)
                # move to temp_scene for faster generation of next ways
#                self.scene.objects.unlink(way.object)
#                self.temp_scene.objects.link(way.object)
            self.process+=self.process_step

    def createObjects(self):
        if debug:
            debugger.debug('Creating objects ...')
        for id in self.nodes:
            node = self.nodes[id]
            node.generate()
#            if node.object:
#                self.setLayer(node)
                # move to temp_scene for faster generation of next ways
#                self.scene.objects.unlink(node.object)
#                self.temp_scene.objects.link(node.object)

    def sortAreas(self):
        if debug:
            debugger.debug('Z-sorting areas ...' )

        way_offset = 0.0
        max_offset = self.offset
        for way in self.ways['area']:
            if way.object:
                way_offset = self.sortCollidingWaysByAreaSize(way)
                if max_offset<way_offset:
                    max_offset = way_offset

        self.offset = max_offset

    def sortRoads(self):
        if debug:
            debugger.debug('Z-sorting roads ...' )

        max_offset = self.offset+OFFSET_STEP
        for way in self.ways['road']:
            if way.object:
                way.setOffset(self.getRoadOffset(way))

        self.offset = max_offset

    def getRoadOffset(self,way):
        colliding = self.getCollidingWays(way,'area','offset')
        if len(colliding)>0:
            offset = colliding[0].offset
            for i in range(0,len(ROADS_SORT_ORDER)):
                if (way.type[2] and way.type[2]==ROADS_SORT_ORDER[i]) or (way.type[1] and way.type[1]==ROADS_SORT_ORDER[i]):
                    return offset+(OFFSET_STEP*i)
            return offset
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
        
        selectObject(self.ground,self.scene)
        selectMesh()
        
        bpy.ops.mesh.edge_face_add()
        bpy.ops.uv.unwrap()

        deselectMesh()
        self.ground.location[2] = -OFFSET_STEP

        # Material
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

        self.scene.camera = self.camera

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
        if debug:
            debugger.debug("parsing ways ...")

        areas = []
        buildings = []
        roads = []
        by_id = {}
        
        xml_ways = xml.getElementsByTagName('way')
        for i in range(0,xml_ways.length):
            way = Way(xml_ways.item(i),self)
            by_id[way.id] = way
            if way.type[0]=='area':
                areas.append(way)
            elif way.type[0]=='building':
                buildings.append(way)
            elif way.type[0]=='road':
                roads.append(way)

        return {'area':areas,'building':buildings,'road':roads,'by_id':by_id,'sorted':[]}

    def getNodeRefs(self,xml):            
        refs = []
        xml_nds = xml.getElementsByTagName('nd')
        for i in range(0,xml_nds.length):
            id = xml_nds.item(i).attributes['ref'].value
            if id in self.nodes:
                node = self.nodes[id]
                refs.append(node)

        return refs

    def getTags(self,xml):
        tags = {}
        xml_tags = xml.getElementsByTagName('tag')
        for i in range(0,xml_tags.length):
            tag = Tag(xml_tags.item(i),self)
            tags[tag.name] = tag

        return tags

    def getCoordinates(self,latLonEle,use_bounds = True):
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

        return co

    def sortCollidingWaysByAreaSize(self,way):
        way_offset = self.offset
        if way.id not in self.ways['sorted']:
            colliding = self.getCollidingWays(way,way.type[0])
            if len(colliding)>0:
                for i in range(0,len(colliding)):
                    way_offset = self.offset + (i*OFFSET_STEP)
                    colliding[i].setOffset(way_offset)

                    # mark as sorted so it wont be sorted again
                    self.ways['sorted'].append(colliding[i].id)

        return way_offset

    def getCollidingWays(self,way,type,sort_by='area',reverse=True):
        from operator import attrgetter
        colliding = []
        if way.type[0] and way.type[0]==type:
            colliding.append(way)
        
        if type in self.ways:
            for c_way in self.ways[type]:
                if c_way.object and c_way!=way:
                    if self.waysCollide(way,c_way):
                        colliding.append(c_way)

        colliding.sort(key=attrgetter(sort_by),reverse=reverse)
        return colliding

    def waysCollide(self,way_a,way_b):
        collide = (way_a.bounds[0][0] < way_b.bounds[1][0]) and (way_a.bounds[1][0] > way_b.bounds[0][0]) and (way_a.bounds[0][1] < way_b.bounds[1][1]) and (way_a.bounds[1][1] > way_b.bounds[0][1])
        return collide

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
    area = 0.0
    bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
    offset = 0.0
    level = 0
    
    def __init__(self,xml,osm):
        self.osm = osm
        self.id = xml.attributes['id'].value
        self.tags = self.osm.getTags(xml)
        self.nodes = self.osm.getNodeRefs(xml)
        self.area = 0.0
        self.bounds = (Vector((0.0,0.0)),Vector((0.0,0.0)))
        self.offset = 0.0
        self.level = 0
        self.setLevel()
        self.setType()
        self.setName()

    def setLevel(self):
        if 'level' in self.tags:
            try:
                self.level = char(int(self.tags['level'].value))
            except:
                self.level = -1

    def setType(self):
        self.type = [None,None,None]
        if BUILDING_TAG in self.tags:
            self.type[0] = 'building'
            self.type[1] = self.tags[BUILDING_TAG].value
            if 'height' in self.tags:
                self.height = getMeters(self.tags['height'].value)
            else:
                self.height = DEFAULT_BUILDING_HEIGHT
        
        if ROAD_TAG in self.tags:
            self.type[0] = 'road'
            self.type[1] = self.tags[ROAD_TAG].value
            if 'lanes' in self.tags:
                self.width = LANE_WIDTH*float(self.tags['lanes'].value)
            else:
                self.width = LANE_WIDTH

        if CYCLEWAY_TAG in self.tags:
            if self.tags[CYCLEWAY_TAG].value=='track': # Only standalone cycleways should be created
                self.type[0] = 'road'
                self.type[1] = CYCLEWAY_TAG
                self.type[2] = self.tags[CYCLEWAY_TAG].value
                self.width = CYCLEWAY_WIDTH

        if RAILWAY_TAG in self.tags:
            self.type[0] = 'road'
            self.type[1] = RAILWAY_TAG
            self.type[2] = self.tags[RAILWAY_TAG].value
            self.width = RAILWAY_WIDTH

        for name in AREA_TAGS:
            if name in self.tags:
                self.type[0] = 'area'
                if self.tags[name].value!='yes':
                    self.type[1] = name
                    self.type[2] = self.tags[name].value
    
    def setName(self):     
        if 'name' in self.tags:
            self.name = self.tags['name'].value
        else:
            self.name = '%s_%s' % (self.type[0],self.id)

    def generate(self):
        if self.level>=0 and self.type[0]:
            if debug:
                debugger.debug('%3.2f' % (self.osm.process) +'% ' + self.name)
            self.createObject()
            selectObject(self.object,self.osm.scene)
            self.create()
            self.setMaterial()
            deselectObject(self.object)

            self.area = self.object.dimensions[0]*self.object.dimensions[1]
            self.bounds[0][0] = self.object.location[0]-(self.object.dimensions[0]/2)
            self.bounds[1][0] = self.object.location[0]+(self.object.dimensions[0]/2)
            self.bounds[0][1] = self.object.location[1]-(self.object.dimensions[1]/2)
            self.bounds[1][1] = self.object.location[1]+(self.object.dimensions[1]/2)

            # align objects along center edge
            self.alignObjects()

    def create(self):
        # TODO: look for USAGE_TAGS groups and place them on top of building, on every node for lines or in object center for areas
        # TODO: allow for scalable or repeatable groups in between nodes for lines (cables of powerlines for example)
        # TODO: allow for scatterable groups for natural area types (trees, bushes, etc.)
        if self.type[0]=='building':
            self.createBuilding()
        elif self.type[0]=='area':
            self.createArea()
        elif self.type[0] in ('road','cycleway'):
            self.createStreet()
        
        edge_split = self.object.modifiers.new(name="edge_split",type="EDGE_SPLIT")
        edge_split.split_angle = 40.00


    def createObject(self):
        mesh = bpy.data.meshes.new(self.name)
        self.object = bpy.data.objects.new(self.name,mesh)
        self.object['osm_id'] = self.id
        self.object['osm_types'] = str(self.type)
        self.osm.scene.objects.link(self.object)

    def createBuilding(self):
        # TODO: create uv-coordinates
        from mathutils import geometry
        num = len(self.nodes)-1 # first and last are at the same location, so we do not need the last node
        v_num = num*2
        mesh = self.object.data
        mesh.vertices.add(v_num)
        mesh.edges.add(num*3)
        mesh.faces.add(num)
        
        for i in range(0,num):
            # bottom
            mesh.vertices[i].co = self.nodes[i].co
            mesh.edges[i].vertices = [i,(i+1) % num]

            # top
            mesh.vertices[i+num].co = self.nodes[i].co.copy()
            mesh.vertices[i+num].co[2]+=self.height
            mesh.edges[i+num].vertices = [i+num,((i+1) % num)+num]

            # joining edge
            mesh.edges[v_num+i].vertices = [i,i+num]

            # wall
            if i==num-1: # last one needs inverted direction
                mesh.faces[i].vertices_raw = [i,0,num,v_num-1]
            else:
                mesh.faces[i].vertices_raw = [i,i+1,(i+num+1) % v_num,(i+num) % v_num]

            mesh.faces[i].use_smooth = True
                
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
            mesh.faces[i+num].vertices = [v1,v2,v3]
            mesh.faces[i].use_smooth = True
            mesh.edges[i+(num*3)].vertices = [v1,v2]
            mesh.edges[i+(num*3)+1].vertices = [v2,v3]
            mesh.edges[i+(num*3)+2].vertices = [v3,v1]

        mesh.validate()

        selectMesh()
        bpy.ops.mesh.normals_make_consistent()
        deselectMesh()
        #bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")
        
    def createArea(self):
         # TODO: create uv-coordinates
        num = len(self.nodes)-1 # first and last are at the same location, so we do not need the last node
        mesh = self.object.data
        mesh.vertices.add(num)
        mesh.edges.add(num)
        
        for i in range(0,num):
            mesh.vertices[i].co = self.nodes[i].co
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
            mesh.faces[i].vertices = [v1,v2,v3]
            mesh.faces[i].use_smooth = True
            mesh.edges[i].vertices = [v1,v2]
            mesh.edges[i+1].vertices = [v2,v3]
            mesh.edges[i+2].vertices = [v3,v1]

        mesh.validate()

        #bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

    def createStreet(self):
         # TODO: create uv-coordinates
        from mathutils import Euler
        upvector = Vector((0.0,0.0,1.0))

        num = len(self.nodes)
        v_num = len(self.nodes)*2
        
        mesh = self.object.data
        mesh.vertices.add(v_num)
        mesh.faces.add(num-1)
        mesh.edges.add(num+num+num-2)

        for i in range(0,num):
            if i>0:
                start_v = self.nodes[i-1].co
            else:
                start_v = self.nodes[i].co

            if i<num-1:
                end_v = self.nodes[i+1].co
            else:
                end_v = self.nodes[i].co
                
            normal = (start_v-end_v).normalized().cross(upvector)
            offset = normal*(self.width/2)

            # TODO: on 90° turns or more we have to switch normal direction, maybe keep last normal and check if we switched from <0 to >0?
            
            # position vertices
            ii = i*2
            mesh.vertices[ii].co = self.nodes[i].co+offset # left
            mesh.vertices[ii+1].co = self.nodes[i].co-offset # right

            # joining edge
            mesh.edges[i].vertices = [ii,ii+1]

            if i<num-1: # ignore last node, as it has no side edges
                # left edge
                mesh.edges[i+num].vertices = [ii,ii+2]
                # right edge
                mesh.edges[i+(num*2)-1].vertices = [ii+1,ii+3]

                # face
                mesh.faces[i].vertices_raw = [ii,ii+1,ii+3,ii+2]
                mesh.faces[i].use_smooth = True
                
        mesh.validate()

        #bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

    def alignObjects(self):
        from mathutils import Euler
        upvector = Vector((0.0,0.0,1.0))
        
        for i in range(0,len(self.nodes)):
            # check for referenced objects and align them with center edge on xy plane, means rotate on z-axis only
            if self.nodes[i].object:
                if i>0:
                    start_v = self.nodes[i-1].co
                else:
                    start_v = self.nodes[i].co

                if i<len(self.nodes)-1:
                    end_v = self.nodes[i+1].co
                else:
                    end_v = self.nodes[i].co

                normal = (start_v-end_v).normalized().cross(upvector)
                rot = normal.to_track_quat('X','Z').to_euler()
                self.nodes[i].object.rotation_euler = rot
                
                # offset the object to the side so it next to a road
                if self.width>0:
                    offset = normal*(self.width/2)
                    if RIGHT_HAND_TRAFFIC:
                        self.nodes[i].object.location-=offset
                    else:
                        self.nodes[i].object.location-=offset

    def setMaterial(self):
        bpy.ops.object.material_slot_add()
        if self.type[2] and (self.type[2] in bpy.data.materials):
            self.object.material_slots[0].material = bpy.data.materials[self.type[2]]
        elif self.type[1] and (self.type[1] in bpy.data.materials):
            self.object.material_slots[0].material = bpy.data.materials[self.type[1]]
        elif self.type[0] and (self.type[0] in bpy.data.materials):
            self.object.material_slots[0].material = bpy.data.materials[self.type[0]]
        else:
            mat = None
            if self.type[2]:
                mat = bpy.data.materials.new(self.type[1])
            elif self.type[1]:
                mat = bpy.data.materials.new(self.type[2])
            elif self.type[0]:
                mat = bpy.data.materials.new(self.type[0])

            if mat:
                self.object.material_slots[0].material = mat

    def setOffset(self,offset):
        if self.object:
            self.offset = offset
            self.object.location[2] = offset
            

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

    def __init__(self,xml,osm):
        self.osm = osm
        self.id = xml.attributes['id'].value
        self.lat = float(xml.attributes['lat'].value)
        self.lon = float(xml.attributes['lon'].value)
        self.object = None
        self.name = None
        self.level = 0

        if 'ele' in xml.attributes:
            self.ele = float(xml.attributes['ele'].value)

        self.co = self.osm.getCoordinates((self.lat,self.lon,self.ele))
        self.tags = self.osm.getTags(xml)
        self.setLevel()
        self.setType()
        self.setName()

    def setLevel(self):
        if 'level' in self.tags:
            try:
                self.level = char(int(self.tags['level'].value))
            except:
                self.level = -1

    def setType(self):
        self.type = [None,None,None]
        if ROAD_TAG in self.tags:
            self.type[0] = 'object'
            self.type[1] = self.tags[ROAD_TAG].value

        if AEROWAY_TAG in self.tags:
            self.type[0] = 'object'
            self.type[1] = AEROWAY_TAG
            self.type[2] = self.tags[AEROWAY_TAG].value

        if RAILWAY_TAG in self.tags:
            self.type[0] = 'object'
            self.type[1] = RAILWAY_TAG
            self.type[2] = self.tags[RAILWAY_TAG].value

        for name in USAGE_TAGS:
            if name in self.tags:
                self.type[0] = 'object'
                self.type[1] = name
                self.type[2] = self.tags[name].value

    def setName(self):
        if self.type[0] and self.type[1]:
            self.name = self.type[1]+'_'+self.id

    def generate(self):
         if self.level>=0 and self.type[0]:
            self.createObject()
#            selectObject(self.object,self.osm.scene)
            self.create()
#            deselectObject(self.object)

    def createObject(self):
        self.object = bpy.data.objects.new(self.name,None)
        self.object['osm_id'] = self.id
        self.object['osm_types'] = str(self.type)
        self.osm.scene.objects.link(self.object)

    def create(self):
        self.object.location = self.co
        if self.type[0]=='object' and self.type[1]:
            self.object.dupli_type = 'GROUP'
            if self.type[1] in bpy.data.groups:
                self.object.dupli_group = bpy.data.groups[self.type[1]]
            elif self.type[2] and self.type[2] in bpy.data.groups:
                self.object.dupli_group = bpy.data.groups[self.type[2]]
            else:
                if self.type[2]:
                    group = bpy.data.groups.new(self.type[2])
                elif self.type[1]:
                    group = bpy.data.groups.new(self.type[1])
                self.object.dupli_group = group