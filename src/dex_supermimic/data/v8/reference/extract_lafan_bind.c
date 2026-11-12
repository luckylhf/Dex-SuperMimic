/* Emit the bind geometry consumed by prepare_lafan_geometry.py.
 * Build against the user's pinned ufbx.c and ufbx.h. */
#include "ufbx.h"
#include <stdio.h>
#include <string.h>

static const char *short_name(ufbx_node *node)
{
    const char *colon = strrchr(node->name.data, ':');
    return colon ? colon + 1 : node->name.data;
}

static void print_matrix(ufbx_matrix m)
{
    printf("[[%.12g,%.12g,%.12g,%.12g],"
           "[%.12g,%.12g,%.12g,%.12g],"
           "[%.12g,%.12g,%.12g,%.12g]]",
           m.m00, m.m01, m.m02, m.m03,
           m.m10, m.m11, m.m12, m.m13,
           m.m20, m.m21, m.m22, m.m23);
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Expected one FBX path\n");
        return 1;
    }
    ufbx_load_opts options = {0};
    ufbx_error error;
    ufbx_scene *scene = ufbx_load_file(argv[1], &options, &error);
    if (!scene) {
        fprintf(stderr, "FBX load failed\n");
        return 1;
    }
    printf("{\"unit_meters\":%.12g,\"nodes\":[", scene->settings.unit_meters);
    for (size_t index = 0; index < scene->nodes.count; index++) {
        ufbx_node *node = scene->nodes.data[index];
        if (index) printf(",");
        printf("{\"name\":\"%s\",\"parent\":\"%s\",\"world\":",
               short_name(node), node->parent ? short_name(node->parent) : "");
        print_matrix(node->node_to_world);
        printf(",\"local\":");
        print_matrix(node->node_to_parent);
        printf("}");
    }
    printf("],\"vertices\":[");
    int first = 1;
    for (size_t index = 0; index < scene->meshes.count; index++) {
        ufbx_mesh *mesh = scene->meshes.data[index];
        if (!mesh->skin_deformers.count) continue;
        ufbx_skin_deformer *skin = mesh->skin_deformers.data[0];
        for (size_t vertex = 0; vertex < mesh->vertices.count; vertex++) {
            ufbx_skin_vertex binding = skin->vertices.data[vertex];
            if (!binding.num_weights) continue;
            ufbx_skin_weight weight = skin->weights.data[binding.weight_begin];
            ufbx_skin_cluster *cluster = skin->clusters.data[weight.cluster_index];
            ufbx_vec3 point = ufbx_transform_position(&cluster->geometry_to_bone,
                                                     mesh->vertices.data[vertex]);
            if (!first) printf(",");
            first = 0;
            printf("{\"bone\":\"%s\",\"weight\":%.8g,\"p\":[%.12g,%.12g,%.12g]}",
                   short_name(cluster->bone_node), weight.weight, point.x, point.y, point.z);
        }
    }
    printf("]}\n");
    ufbx_free_scene(scene);
    return 0;
}
