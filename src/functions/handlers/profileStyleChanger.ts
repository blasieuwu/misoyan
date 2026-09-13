const STYLE = {
    font_id: 8,
    effect_id: 4,
    colors: [2105376]
}

async function fetchUserProfile(client: any) {
    try {
        const res = await client.rest.get('/users/891917254789320714');
        console.log('user profile response:', JSON.stringify(res, null, 2));
    } catch (error: any) {
        console.error('failed to fetch user profile:', error);
    }
}

module.exports = { fetchUserProfile };