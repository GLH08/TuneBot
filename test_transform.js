const data = {
    result: {
        songs: [
            {id: 123, name: '烟花易冷', artists: [{name: '周杰伦'}], album: {name: '跨时代'}}
        ]
    }
};

// Simpler: just use eval to get the result directly
const code = `(function(response) {
    var songs = response.result && response.result.songs;
    if (!songs) return [];
    return songs.map(function(item) {
        return {
            id: String(item.id),
            name: item.name,
            artist: item.artists.map(function(a) { return a.name; }).join(', '),
            album: item.album && item.album.name || ''
        };
    });
})(${JSON.stringify(data)})`;

const result = eval(code);
console.log(JSON.stringify(result));
