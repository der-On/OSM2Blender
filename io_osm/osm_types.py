import bpy
import math
from collections import OrderedDict
from mathutils import geometry
from mathutils import Vector
from io_osm.import_osm import *

AEROWAY_TAG = 'aeroway' # TODO: add way support
BUILDING_TAG = 'building'
BARRIER_TAG = 'barrier'
USAGE_TAGS = ['amenity','shop','office','craft','emergency','tourism','historic','military']
ROAD_TAG = 'highway'
CYCLEWAY_TAG = 'cycleway'
AREA_TAGS = ('area','natural','landuse','leisure')
RAILWAY_TAG = 'railway'
UNIT_SCALES = {'m':1,'ft':0.305}
LAYERS = ['building','area','road','object',None,None,None,None,None,None,None,None,None,None,None,None,None,None,None,None]

ROADS_SORT_ORDER = [None,'cycleway','railway']

EQUATOR_RADIUS = 6378137        # greatest earth radius (equator)
POLE_RADIUS = 6356752.314245    # smallest earth radius (pole)

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
    config_tags = {}

    # config
    latlon_scale = 3.33
    right_hand_traffic = True
    offset_step = 0.001
    lane_width = 3.0
    cycleway_width = 1.0
    railway_width = 1.5
    building_level_height = 5.0
    building_default_levels = 3
    roof_texture_scale = 1.0
    area_texture_scale = 1.0
    file = None

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
        
        self.setConfig()
        self.setConfigTags()

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
        
    def setConfig(self):
        osm = bpy.context.scene.osm
        if osm.traffic_direction == 'right':
            self.right_hand_traffic = True
        else:
            self.right_hand_traffic = False

        self.latlon_scale = osm.latlon_scale
        self.offset_step = osm.offset_step
        self.lane_width = osm.lane_width
        self.cycleway_width = osm.cycleway_width
        self.railway_width = osm.railway_width
        self.building_level_height = osm.building_level_height
        self.building_default_levels = osm.building_default_levels
        self.roof_texture_scale = osm.roof_texture_scale
        self.area_texture_scale = osm.area_texture_scale

    def setConfigTags(self):
        for material in bpy.data.materials:
            for tag in material.osm.tags:
                config_name = tag.name+'='+tag.value
                if config_name in self.config_tags:
                    tag_config = self.config_tags[config_name]
                else:
                    tag_config = TagConfig(tag.name,tag.value)
                    self.config_tags[config_name] = tag_config

                if material not in tag_config.materials:
                    tag_config.materials.append(material)

        for group in bpy.data.groups:
            for tag in group.osm.tags:
                config_name = tag.name+'='+tag.value
                if config_name in self.config_tags:
                    tag_config = self.config_tags[config_name]
                else:
                    tag_config = TagConfig(tag.name,tag.value)
                    self.config_tags[config_name] = tag_config

                if group not in tag_config.groups:
                    tag_config.groups.append(group)
                    

    def getTagConfig(self,name,value):
        full_name = name+'='+value
        undefined_name = name+'='
        if full_name in self.config_tags:
            return self.config_tags[full_name]
        elif undefined_name in self.config_tags:
            return self.config_tags[undefined_name]
        return None

    def generate(self,rebuild):
        self.scene = bpy.context.scene

        # create temporary scene
#        self.temp_scene = bpy.data.scenes.new("OSM_import")
        #bpy.context.scene.background_set = self.temp_scene

        self.nodes = self.getNodes(self.xml)
        self.ways = self.getWays(self.xml)

        deselectObjects(self.scene)

        #self.createGround()
        #self.createCamera()

        self.process_step = 100/len(self.ways['by_id'])

        # generate all node objects
        self.createObjects(rebuild)

        # generate all ways
        self.createWays(rebuild)

        self.sortAreas()
        self.sortRoads()

        # set to layers
        if rebuild==False:
            for i in range(0,20):
                if LAYERS[i]:
                    if LAYERS[i]=='object':
                        self.setToLayer(self.nodes,i,True)
                    elif LAYERS[i] in self.ways:
                        self.setToLayer(self.ways[LAYERS[i]],i)

            updateScene(self.scene)

            if debug:
                debugger.debug("OSM import complete!")
        else:
            updateScene(self.scene)
            if debug:
                debugger.debug('OSM rebuild complete!')

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
        for id in self.ways['by_id']:
            way = self.ways['by_id'][id]
            way.generate(rebuild)
#            if way.object:
#                self.setLayer(way)
                # move to temp_scene for faster generation of next ways
#                self.scene.objects.unlink(way.object)
#                self.temp_scene.objects.link(way.object)
            self.process+=self.process_step

    def createObjects(self,rebuild):
        if debug:
            debugger.debug('Creating objects ...')
        for id in self.nodes:
            node = self.nodes[id]
            node.generate(rebuild)
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

        max_offset = self.offset+self.offset_step
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
                    return offset+(self.offset_step*i)
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
        co[1] = (r/180)*latLonEle[0]*self.latlon_scale
        co[0] = ((r/2)/180)*latLonEle[1]*self.latlon_scale

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
            colliding = self.getCollidingWays(way,way.type[0])
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


class TagConfig():
    name = None
    value = None
    materials = []
    groups = []

    def  __init__(self,name,value):
        self.name = name
        self.value = value
        self.materials = []
        self.groups = []

    def orderMaterials(self):
        self.materials.sort(cmp=self.orderByPriority())

    def orderGroups(self):
        self.groups.sort(cmp=self.orderByPriority())
        
    def orderByPriority(a,b):
        if self.getTagInList(a.osm.tags).priority > self.getTagInList(b.osm.tags).priority:
            return 1
        else:
            return -1

    def getTagInList(self,list):
        for tag in list:
            if tag.name==self.name and tag.value==self.value:
                return tag
        return None        

# TODO: create subclasses for roads,buildings,areas?
class Way():
    id = None
    name = "Way"
    nodes = []
    tags = {}
    type = None
    height = None
    width = 0
    lanes = 1
    levels = 0
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
        self.levels = None
        self.height = None
        self.lanes = 1
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
                self.height = self.osm.getMeters(self.tags['height'].value)
                self.levels = self.height/self.osm.building_level_height
            else:
                self.levels = self.osm.building_default_levels
                #self.height = self.levels*self.osm.building_level_height

        if ROAD_TAG in self.tags:
            self.type[0] = 'road'
            self.type[1] = self.tags[ROAD_TAG].value
            if 'lanes' in self.tags:
                self.lanes = int(self.tags['lanes'].value)
                
            self.width = self.osm.lane_width*self.lanes

        if CYCLEWAY_TAG in self.tags:
            if self.tags[CYCLEWAY_TAG].value=='track': # Only standalone cycleways should be created
                self.type[0] = 'road'
                self.type[1] = CYCLEWAY_TAG
                self.type[2] = self.tags[CYCLEWAY_TAG].value
                self.width = self.osm.cycleway_width

        if RAILWAY_TAG in self.tags:
            self.type[0] = 'road'
            self.type[1] = RAILWAY_TAG
            self.type[2] = self.tags[RAILWAY_TAG].value
            self.width = self.osm.railway_width

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

    def generate(self,rebuild):
        if self.level>=0 and self.type[0]:
            if debug:
                debugger.debug('%3.2f' % (self.osm.process) +'% ' + self.name)
            self.createObject(rebuild)
            if self.object:
                selectObject(self.object,self.osm.scene)
                self.setMaterial(rebuild)
                self.create(rebuild)
                deselectObject(self.object)

                self.setArea()
                self.bounds[0][0] = self.object.location[0]-(self.object.dimensions[0]/2)
                self.bounds[1][0] = self.object.location[0]+(self.object.dimensions[0]/2)
                self.bounds[0][1] = self.object.location[1]-(self.object.dimensions[1]/2)
                self.bounds[1][1] = self.object.location[1]+(self.object.dimensions[1]/2)

                # align objects along center edge
                self.alignObjects()

    def setArea(self):
        for face in self.object.data.faces:
            self.area+=face.area

    def create(self,rebuild):
        # TODO: look for USAGE_TAGS groups and place them on top of building, on every node for lines or in object center for areas
        # TODO: allow for scalable or repeatable groups in between nodes for lines (cables of powerlines for example)
        # TODO: allow for scatterable groups for natural area types (trees, bushes, etc.)
        if self.type[0]=='building':
            self.createBuilding(rebuild)
        elif self.type[0]=='area':
            self.createArea(rebuild)
        elif self.type[0] in ('road','cycleway'):
            self.createRoad(rebuild)

        if rebuild==False:
            edge_split = self.object.modifiers.new(name="edge_split",type="EDGE_SPLIT")
            edge_split.split_angle = 40.00


    def createObject(self,rebuild):
        if rebuild==False:
            mesh = bpy.data.meshes.new(self.name)
            self.object = bpy.data.objects.new(self.name,mesh)
            self.object.osm.id = self.id
            self.object.osm.name = self.name
            for tag in self.tags:
                obj_tag = self.object.osm.tags.add()
                obj_tag.name = self.tags[tag].name
                obj_tag.value = self.tags[tag].value

            self.osm.scene.objects.link(self.object)
        else:
            for object in self.osm.scene.objects:
                if object.osm.id == self.id:
                    self.object = object
                    return

    # TODO: check if a group with the osm-property "name" with same name as the way exists and use that instead of generic mesh
    def createBuilding(self,rebuild):
        from mathutils import geometry
        num = len(self.nodes)-1 # first and last are at the same location, so we do not need the last node
        v_num = num*2
        mesh = self.object.data
        
        # update height from material level height
        material = self.object.material_slots[0].material
        if material:
            if self.height==None: # no explicit height info in way
                self.levels = material.osm.building_default_levels
                self.height = self.levels*material.osm.building_level_height

        if rebuild==False:
            mesh.vertices.add(v_num)
            mesh.edges.add(num*3)
            mesh.faces.add(num)

        # TODO: we have to reverse node order if direction is counter clockwise.
        clockwise = self.isClockwise()
        if clockwise:
            self.nodes.reverse()
            
        for i in range(0,num):
            # bottom
            if rebuild:
                mesh.vertices[i].co = self.nodes[i].co-self.object.location
            else:
                mesh.vertices[i].co = self.nodes[i].co
                mesh.edges[i].vertices = [i,(i+1) % num]
                
            # top
            if rebuild:
                mesh.vertices[i+num].co = self.nodes[i].co.copy()-self.object.location
            else:
                mesh.vertices[i+num].co = self.nodes[i].co.copy()
                mesh.edges[i+num].vertices = [i+num,((i+1) % num)+num]

            mesh.vertices[i+num].co[2]+=self.height            

            # joining edge
            if rebuild==False:
                mesh.edges[v_num+i].vertices = [i,i+num]

            # wall
            if rebuild==False:
                if i==num-1: # last one needs inverted direction
                    mesh.faces[i].vertices_raw = [i,0,num,v_num-1]
                else:
                    mesh.faces[i].vertices_raw = [i,i+1,(i+num+1) % v_num,(i+num) % v_num]

            if rebuild==False:
                mesh.faces[i].use_smooth = True
                mesh.faces[i].material_index = 0

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
            bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        # create uvs
        if rebuild:
            uv_texture = mesh.uv_textures[0]
        else:
            uv_texture = mesh.uv_textures.new()
            
        # facade uvs
        uv_x = 0.0

        # uv factors
        if material:
            level_height = material.osm.building_level_height
            texture_levels = material.osm.building_levels
        else:
            level_height = self.osm.building_level_height
            texture_levels = 1

        height = self.levels/texture_levels
        
        for i in range(0,num):
            uv_face = uv_texture.data[i]
            mesh_face = mesh.faces[i]
            # calculate width of uv face using face area and height
            face_width = mesh_face.area/self.height
            width = face_width/(level_height*texture_levels)

            uv = []
            uv.append((uv_x,height))
            uv.append((uv_x+width,height))
            uv.append((uv_x+width,0.0))
            uv.append((uv_x,0.0))

            # set uvs
            uv_face.uv_raw = (uv[3][0],uv[3][1],uv[2][0],uv[2][1],uv[1][0],uv[1][1],uv[0][0],uv[0][1])

            uv_x+=width

        # roof uvs
        scale = self.osm.roof_texture_scale

        for i in range(num,len(mesh.faces)):
            uv_face = uv_texture.data[i]
            mesh_face = mesh.faces[i]
            if rebuild:
                v1 = (mesh.vertices[mesh_face.vertices[0]].co.copy()*scale)-self.object.location
                v2 = (mesh.vertices[mesh_face.vertices[1]].co.copy()*scale)-self.object.location
                v3 = (mesh.vertices[mesh_face.vertices[2]].co.copy()*scale)-self.object.location
                if len(mesh_face.vertices)==4:
                    v4 = (mesh.vertices[mesh_face.vertices[3]].co.copy()*scale)-self.object.location
                else:
                    v4 = (0.0,0.0)
            else:
                v1 = mesh.vertices[mesh_face.vertices[0]].co.copy()*scale
                v2 = mesh.vertices[mesh_face.vertices[1]].co.copy()*scale
                v3 = mesh.vertices[mesh_face.vertices[2]].co.copy()*scale
                if len(mesh_face.vertices)==4:
                    v4 = mesh.vertices[mesh_face.vertices[3]].co.copy()*scale
                else:
                    v4 = (0.0,0.0)

            uv_face.uv_raw = (v1[0],v1[1],v2[0],v2[1],v3[0],v3[1],v4[0],v4[1])

    def createArea(self,rebuild):
        num = len(self.nodes)-1 # first and last are at the same location, so we do not need the last node
        mesh = self.object.data

        if rebuild==False:
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
                mesh.faces[i].vertices = [v3,v2,v1]
                mesh.faces[i].use_smooth = True
                mesh.edges[i].vertices = [v1,v2]
                mesh.edges[i+1].vertices = [v2,v3]
                if len(mesh.edges)>=i+2:
                    mesh.edges[i+2].vertices = [v3,v1]

            mesh.validate()
            bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

            # create uvs
            uv_texture = mesh.uv_textures.new()
        else:
            uv_texture = mesh.uv_textures[0]
            
        scale = self.osm.area_texture_scale

        for i in range(0,len(mesh.faces)):
            uv_face = uv_texture.data[i]
            mesh_face = mesh.faces[i]
            v1 = mesh.vertices[mesh_face.vertices[0]].co.copy()*scale
            v2 = mesh.vertices[mesh_face.vertices[1]].co.copy()*scale
            if len(mesh_face.vertices)>=3:
                v3 = mesh.vertices[mesh_face.vertices[2]].co.copy()*scale
            else:
                v3 = (0.0,0.0)
            if len(mesh_face.vertices)==4:
                v4 = mesh.vertices[mesh_face.vertices[3]].co.copy()*scale
            else:
                v4 = (0.0,0.0)

            uv_face.uv_raw = (v1[0],v1[1],v2[0],v2[1],v3[0],v3[1],v4[0],v4[1])

    def createRoad(self,rebuild):
        from mathutils import Euler
        upvector = Vector((0.0,0.0,1.0))

        num = len(self.nodes)
        v_num = len(self.nodes)*2

        mesh = self.object.data

        # rebuild width from material
        material = self.object.material_slots[0].material
        if material and material.osm.base_type=='road':
            self.width = material.osm.lane_width*self.lanes

        if rebuild==False:
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

            if rebuild:
                mesh.vertices[ii].co = self.nodes[i].co+offset-self.object.location # left
                mesh.vertices[ii+1].co = self.nodes[i].co-offset-self.object.location # right
            else:
                mesh.vertices[ii].co = self.nodes[i].co+offset # left
                mesh.vertices[ii+1].co = self.nodes[i].co-offset # right

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

        if rebuild==False:
            mesh.validate()
            bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

        # create uvs
        if rebuild:
            uv_texture = mesh.uv_textures[0]
        else:
            uv_texture = mesh.uv_textures.new()

        uv_y = 0.0

        if material and material.osm.base_type=='road':
            texture_lanes = material.osm.lanes
        else:
            texture_lanes = 2

        # uv height factors
        width = self.lanes/texture_lanes
        hf = 1/(self.width/self.lanes)

        for i in range(0,len(uv_texture.data)):
            uv_face = uv_texture.data[i]
            mesh_face = mesh.faces[i]
            # calculate height of uv face using face area and road width
            height = hf*(mesh_face.area/self.width)

            # set uvs
            uv_face.uv_raw = (0.0,uv_y+height,width,uv_y+height,width,uv_y,0.0,uv_y)

            uv_y+=height
            

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
                    if self.osm.right_hand_traffic:
                        self.nodes[i].object.location-=offset
                    else:
                        self.nodes[i].object.location-=offset
    
    def setMaterial(self,rebuild):
        # facade
        if rebuild==False:
            bpy.ops.object.material_slot_add()
            
        building = False
        road = False
        area = False
        
        if self.type[0]=='building':
            building = True
            bpy.ops.object.material_slot_add() # roof
        elif self.type[0]=='road':
            road = True
        elif self.type[0]=='area':
            area = True

        mat = None
        roof_mat = None

        priority = 0
        
        for name in self.tags:
            tag = self.tags[name]
            tag_config = self.osm.getTagConfig(tag.name,tag.value)
            if tag_config:
                for material in tag_config.materials:
                    mat_tag = tag_config.getTagInList(material.osm.tags)
                    tag_priority = mat_tag.priority

                    if tag_priority>=priority:
                        if building and material.osm.base_type == 'building':
                            if material.osm.building_part=='facade':
                                mat = material
                            elif material.osm.building_part in ('flat_roof','sloped_roof'):
                                roof_mat = material
                        if road and material.osm.base_type == 'road':
                            # prefer materials with matching lanes
                            if mat==None or mat.osm.lanes!=self.lanes:
                                mat = material
                        if area and material.osm.base_type == 'area':
                            mat = material

                        priority = tag_priority
                        
        self.object.material_slots[0].material = mat
        if building:
            self.object.material_slots[1].material = roof_mat

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

    def generate(self,rebuild):
         if self.level>=0 and self.type[0]:
            self.createObject(rebuild)
#            selectObject(self.object,self.osm.scene)
            self.create(rebuild)
#            deselectObject(self.object)

    def createObject(self,rebuild):
        if rebuild==False:
            self.object = bpy.data.objects.new(self.name,None)
            self.object.osm.id = self.id
            self.object.osm.name = self.name
            for tag in self.tags:
                obj_tag = self.object.osm.tags.add()
                obj_tag.name = self.tags[tag].name
                obj_tag.value = self.tags[tag].value
                
            self.osm.scene.objects.link(self.object)
        else:
            for object in self.osm.scene.objects:
                if object.osm.id == self.id:
                    self.object = object
                    return
        
    def create(self,rebuild):
        self.object.location = self.co
        group = None
        priority = 0

        if self.type[0]=='object':
            for name in self.tags:
                tag = self.tags[name]
                tag_config = self.osm.getTagConfig(tag.name,tag.value)
                if tag_config:
                    for tag_group in tag_config.groups:
                        group_tag = tag_config.getTagInList(tag_group.osm.tags)
                        tag_priority = group_tag.priority

                        if tag_priority>=priority:
                            group = tag_group
                            priority = tag_priority

        if group:
            self.object.dupli_type = 'GROUP'
            self.object.dupli_group = group