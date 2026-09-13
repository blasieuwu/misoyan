const STYLE = {
    font_id: 8,
    effect_id: 4,
    colors: [2105376]
}

async function applyDisplayNameStyle(client: any) {
    const guilds = client.guilds.cache.map((g: any) => g.id);
    if (!guilds.length) return;

    const body = {
        display_name_styles: {
            font_id: STYLE.font_id,
            effect_id: STYLE.effect_id,
            colors: STYLE.colors
        }
    };

    for (const guild of guilds) {
        try {
            const res = await client.rest.patch(`/guilds/${guild}/members/@me`, { body });
            console.log(`applied display name style for guild ${guild} | response:`, JSON.stringify(res));
        } catch (error: any) {
            console.error(`failed to apply display name style for guild ${guild} | error: ${error}`);
        }
    }
    console.log('finished applying display name style for all guilds');
}

module.exports = { applyDisplayNameStyle };