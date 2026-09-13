const STYLE = {
    font_id: 8,
    effect_id: 4,
    colors: [2105376]
}

async function applyDisplayNameStyle(client: any) {
    const body = {
        display_name_style: {
            font_id: STYLE.font_id,
            effect_id: STYLE.effect_id,
            colors: STYLE.colors
        }
    };

    try {
        const res = await client.rest.patch('/users/@me', { body });
        console.log(`applied nested style | response:`, JSON.stringify(res));
    } catch (error: any) {
        console.error(`failed to apply nested style | error: ${error}`);
    }
}

module.exports = { applyDisplayNameStyle };