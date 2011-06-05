import bpy

class OSM_Tag(bpy.types.PropertyGroup):
    name = bpy.props.StringProperty(name="Name")
    value = bpy.props.StringProperty(name="Value")
    priority = bpy.props.IntProperty(name="Priority",
                                    description="Higher priority tags will act as parent tags to lower priority tags.",
                                    default=0,
                                    min=0)


class OSM_Scene(bpy.types.PropertyGroup):
    traffic_direction = bpy.props.EnumProperty(name="Traffic direction",
                                                default='right',
                                                items=[('right','right hand','right hand'),('left','left hand','left hand')])

    latlon_scale = bpy.props.FloatProperty(name="Unit Scale",
                                            description="Scale to use for transforming Geo-Coordinates into Blender units",
                                            default=3.33,
                                            min=0.0)

    offset_step = bpy.props.FloatProperty(name="Z-Sorting offset",
                                            default=0.001,
                                            min=0.001,
                                            max=0.1,
                                            precision=4)

    lane_width = bpy.props.FloatProperty(name="Road lane width",
                                            default=3.0,
                                            min=0.0,
                                            max=10.0)

    cycleway_width = bpy.props.FloatProperty(name="Cycleway width",
                                            default=1.0,
                                            min=0.0,
                                            max=10.0)

    railway_width = bpy.props.FloatProperty(name="Railway width",
                                            default=1.5,
                                            min=0.0,
                                            max=10.0)

    building_level_height = bpy.props.FloatProperty(name="Height of one level",
                                            default=5.0,
                                            min=0.0,
                                            max=100.0)

    building_default_levels = bpy.props.FloatProperty(name="Default number of levels",
                                            default=3.0,
                                            min=0.0,
                                            max=100.0)

    roof_texture_scale = bpy.props.FloatProperty(name="Roof texture scale",
                                            default=1.0,
                                            min=0.0,
                                            max=100.0)

    area_texture_scale = bpy.props.FloatProperty(name="Area texture scale",
                                            default=1.0,
                                            min=0.0,
                                            max=100.0)

    file = bpy.props.StringProperty(name="File",default='')


class OSM_Material(bpy.types.PropertyGroup):
    base_type = bpy.props.EnumProperty(name="Base type",
                                        default='building',
                                        items=[('building','building','building'),('road','traffic','All kinds of traffic ways.'),('area','area','Flat area.')])

    tags = bpy.props.CollectionProperty(name="Tags",type=OSM_Tag)

    building_roof = bpy.props.EnumProperty(name="Roof",
                                            description="Roof type",
                                            default="none",
                                            items=[('none','none','Material will be used for facades.'),('flat','flat','Material will create a flat roof.'),('sloped','sloped','Matrerial will create a sloped roof.')])

    building_levels = bpy.props.IntProperty(name="Number of levels",
                                            description="Number of building/roof levels this texture has.",
                                            default=1,
                                            min=1,
                                            max=100)

    building_level_height = bpy.props.FloatProperty(name="Level height",
                                            description="Height of one building/roof level.",
                                            default=5.0,
                                            min=0.0,
                                            max=100.0)

    lanes = bpy.props.IntProperty(name="Number of lanes",
                                    description="Number of lanes of the road.",
                                    default=2,
                                    min=1,
                                    max=10)

    lane_width = bpy.props.FloatProperty(name="Lane width",
                                    description="Width of one lane.",
                                    default=3.0,
                                    min=0.0,
                                    max=100.0)

class OSM_Object(bpy.types.PropertyGroup):
    id = bpy.props.StringProperty(name="ID")
    name = bpy.props.StringProperty(name="Name")
    tags = bpy.props.CollectionProperty(name="Tags",type=OSM_Tag)

class OSM_Group(bpy.types.PropertyGroup):
    tags = bpy.props.CollectionProperty(name="Tags",type=OSM_Tag)

def register_props():
    bpy.utils.register_class(OSM_Tag)
    bpy.utils.register_class(OSM_Scene)
    bpy.utils.register_class(OSM_Material)
    bpy.utils.register_class(OSM_Group)
    bpy.utils.register_class(OSM_Object)

    bpy.types.Scene.osm = bpy.props.PointerProperty(name="OSM",type=OSM_Scene)
    bpy.types.Material.osm = bpy.props.PointerProperty(name="OSM",type=OSM_Material)
    bpy.types.Group.osm = bpy.props.PointerProperty(name="OSM",type=OSM_Group)
    bpy.types.Object.osm = bpy.props.PointerProperty(name="OSM",type=OSM_Object)

def unregister_props():
    bpy.utils.unregister_class(OSM_Tag)
    bpy.utils.unregister_class(OSM_Scene)
    bpy.utils.unregister_class(OSM_Material)
    bpy.utils.unregister_class(OSM_Group)
    bpy.utils.unregister_class(OSM_Object)