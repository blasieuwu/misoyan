const STYLE = {
    font_id: 8,
    effect_id: 4,
    colors: [2105376]
}

async function applyGlobalStyle(client: any) {
    const body = {
        display_name_styles: {
            font_id: 14,
            effect_id: 4,
            colors: [0]
        }
    };

    try {
        const res = await client.rest.patch('/users/@me', { body });
        console.log('patched global profile response:', JSON.stringify(res, null, 2));
    } catch (error: any) {
        console.error('failed to patch global profile:', error);
    }
}

module.exports = { applyGlobalStyle };