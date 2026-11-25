// Bauteil-Material mit Schnittebene: alles oberhalb von cutZ (Weltkoordinate y = Höhe über der Platte)
// wird nicht gezeichnet. Ohne Schnitt liegt cutZ weit oben.
void MAIN()
{
    if (VAR_WORLD_POSITION.y > cutZ)
        discard;
    BASE_COLOR = vec4(baseColor.rgb, 1.0);
    ROUGHNESS = 0.5;
    METALNESS = 0.0;
}
