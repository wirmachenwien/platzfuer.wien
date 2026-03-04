;
jQuery(document).ready(function()
{
	// Add autocompleting to WPFTS Custom Search widgets
	jQuery('.search-form.wpfts_autocomplete').each(function(i, v)
	{
		let formElement = v;
		let inp = jQuery('input[name="s"]', v);

		jQuery(inp).autocomplete({
			source: function(request, response)
			{
				const formData = new FormData(formElement);
				const fd = {};

				for (const [key, value] of formData.entries()) {
					fd[key] = value;
				}
				fd['s'] = request.term;

				jQuery.ajax({
					method: 'POST',
					url: document.wpfts_ajaxurl,
					dataType: "json",
					data: {
						action: 'wpfts_autocomplete',
						form_data: fd,
					},
					success: function(data) {
						if (data && (data.length > 0)) {
							response(data);
						} else {
							let nodata = [
								{'label': '<i>No results found</i>'}
							];
							response(nodata);
						}
					}
				});
			},
			minLength: 1,
			delay: 300,
			select: function( event, ui ) {
				var t = jQuery('<textarea />').html(ui.item.label).text();
				// Remove <sup>
				t = t.replace(/<sup>[^<]*<\/sup>?/gm, '');
				
				// Remove all HTML tags
				t = t.replace(/<[^>]*>?/gm, '');
				
				//inp.val(t);
				
				if ('link' in ui.item) {
					document.location.href = ui.item.link;
				}
				
				event.preventDefault();
				return false;
			},
			focus: function( event, ui ) {
				var t = jQuery('<textarea />').html(ui.item.label).text();
				// Remove <sup>
				t = t.replace(/<sup>[^<]*<\/sup>?/gm, '');
				
				// Remove all HTML tags
				t = t.replace(/<[^>]*>?/gm, '');				
				
				//inp.val(t);
				event.preventDefault();
				return false;
			},
			create: function (event,ui) {
				jQuery(this).data('ui-autocomplete')._renderItem = function(ul, item)
				{
					var str = '<li><a>' + item.label + '</a></li>';
					return jQuery(str).appendTo(ul);
				};
			}
		});

	});

});


jQuery(document).ready(function()
{
	let islands = [];
	let mainNode = null;

	function getWords(text) {
		// Replace utf apostrophe to ASCII
		text = text.replace(/[\u00b4\u2018\u2019]/, "'");
		let regex = new RegExp(/([\u00C0-\u1FFF\u2C00-\uD7FF\w][\u00C0-\u1FFF\u2C00-\uD7FF\w']*[\u00C0-\u1FFF\u2C00-\uD7FF\w]+|[\u00C0-\u1FFF\u2C00-\uD7FF\w]+)/, 'g');
		let words = text.matchAll(regex);
		
		let ws = [];
		for (let w of words) {
			ws.push([w[0], w['index']]);
		}
		
		return ws;
	}
	
	function traverseSubNodes(node, level = 0) {
		// Проходим по всем дочерним узлам
		let textNodes = [];
		let is_has_own_texts = false;
		for (let i = 0; i < node.childNodes.length; i++) {
			const childNode = node.childNodes[i];
	
			// Если узел - текст, добавляем в список текстов
			if (childNode.nodeType === Node.TEXT_NODE) {
				let tx = childNode.textContent.trim();
				if (tx.length > 0) {
					// Find words
					let tx2 = getWords(childNode.textContent); // Not trimmed version to get correct offsets
					if (tx2 && (tx2.length > 0)) {
						textNodes.push([childNode, tx2, level, level, i]);	// node, texts, log_level, act_level, i
						is_has_own_texts = true;
					}
				}
			} else {
				if (childNode.nodeType === Node.ELEMENT_NODE) {
					// Если узел - элемент, выводим его тип
					//console.log('Элемент: ', childNode.tagName);
	
					// Ignore some nodes
					if (['META', 'SCRIPT', 'STYLE', 'FRAME', 'IFRAME'].indexOf(childNode.tagName.toUpperCase()) < 0) {
						// Valid node
						// Рекурсивно вызываем функцию для дочерних узлов элемента
						let subsinfo = traverseSubNodes(childNode, level + 1);
						for (let subn of subsinfo) {
							subn[4] = i;
							textNodes.push(subn);
						}
					}
				}
			}
		}

		// Check collected list of nodes
		let resNodes = [];
		let i = 0;
		while (i < textNodes.length) {
			let cnode = textNodes[i];
			if (cnode[2] - level >= 3) {
				// Move those nodes to the island
				let nn = cnode[4];
				let island = [];
				island.push(cnode);
				let n_words = cnode[1].length;
				i ++;
				while (i < textNodes.length) {
					let cnode2 = textNodes[i];
					if (cnode2[4] == nn) {
						// Same island
						island.push(cnode2);
						n_words += cnode2[1].length;
						i ++;
					} else {
						// Island beach
						i --;
						break;
					}
				}
				// Save island to the list of islands
				islands.push([island, n_words]);
			} else {
				if (level == cnode[2]) {
					// This node is 100% ours
					//cnode[2] = level;
					resNodes.push(cnode);
				} else {
					// This node is coming from down, but it is not that deep
					if (is_has_own_texts) {
						// We can merge this node to our level
						cnode[2] = level;
						resNodes.push(cnode);
					} else {
						// Since we have no our own text nodes, we can not merge subnodes
						// And we have to move them to upper level with those 
						// original logic level
						resNodes.push(cnode);
					}
				}
			}
			i ++;
		}

		if (level == 0) {
			// Convert upper textNodes to the islands
			let i = 0;
			while (i < resNodes.length) {
				let cnode = resNodes[i];
				// Move those nodes to the island
				let nn = cnode[4];
				let island = [];
				island.push(cnode);
				let n_words = cnode[1].length;
				i ++;
				while (i < resNodes.length) {
					let cnode2 = resNodes[i];
					if (cnode2[4] == nn) {
						// Same island
						island.push(cnode2);
						n_words += cnode2[1].length;
						i ++;
					} else {
						// Island beach
						break;
					}
				}
				// Save island to the list of islands
				islands.push([island, n_words]);
			}
			resNodes = [];
		}

		return resNodes;
	}

	function findGoodNodes(sw, as_query = false, limit = -1, min_words = 1)
	{
		let goodNodes = [];

		// Jump over all islands to find the same word sequence
		for (let i = 0; i < islands.length; i ++) {
			let island = islands[i];

			if (island[1] < min_words) {
				// Ignore islands with less than min_words words
				continue;
			}

			let is_found = false;
			let is_stop = false;
			for (let wi = 0; wi < island[0].length; wi ++) {
				let node = island[0][wi];
				for (let ni = 0; ni < node[1].length; ni ++) {
					if ((sw[0][0] == node[1][ni][0]) || (as_query && (sw[0][0].toLowerCase() == node[1][ni][0].toLowerCase()))) {

						// First word was found!
						let startInfo = [node[0], node[1][ni][1]];	// node, offset
						let sw_i = 1;
						let is_break = false;
						let ni_start = ni + 1;

						if (sw_i >= sw.length) {	// This was true when search phrase is 1 word long
							// We have reached the end of the search phrase
							goodNodes.push([
								startInfo, 
								[
									node[0], node[1][ni][1] + node[1][ni][0].length
								]
							]);
							is_found = true;
						} else {
							// Need to search further
							for (let wi2 = wi; wi2 < island[0].length; wi2 ++) {
								let node2 = island[0][wi2];
								for (let ni2 = ni_start; ni2 < node2[1].length; ni2 ++) {
									if (sw_i < sw.length) {
										if ((sw[sw_i][0] == node2[1][ni2][0]) || (as_query && (sw[sw_i][0].toLowerCase() == node2[1][ni2][0].toLowerCase()))) {
											// still good
											sw_i ++;
											if (sw_i >= sw.length) {
												// We have reached the end of the search phrase
												goodNodes.push([
													startInfo, 
													[
														node2[0], node2[1][ni2][1] + node2[1][ni2][0].length
													]
												]);
												// We will continue from the tail
												wi = wi2;
												ni = ni2 + 1;
			
												is_found = true;
												is_break = true;
												break;		
											}
										} else {
											// We found not good word
											is_found = false;
											is_break = true;
											break;
										}
									} else {
										// We found the phrase!
										goodNodes.push([
											startInfo, 
											[
												node2[0], node2[1][ni2 - 1][1] + node2[1][ni2 - 1][0].length
											]
										]);
										// We will continue from the tail
										wi = wi2;
										ni = ni2;
	
										is_found = true;
										is_break = true;
										break;
									}
								}
								if (is_break) {
									break;
								}
								ni_start = 0;
							}	
						}
					}
					if (is_found) {
						if ((limit > 0) && (goodNodes.length >= limit)) {
							// Stop search
							is_stop = true;
						}
						is_found = false;
					}
					if (is_stop) {
						break;
					}
				}
				if (is_stop) {
					break;
				}
			}
		}

		return goodNodes;
	}

	function highlightSentence(sentence, classV = 'wpfts-highlight-sentence')
	{
		let sw = getWords(sentence);

		let nodePaths = findGoodNodes(sw, false, -1);

		if (nodePaths.length > 0) {
			// Select and highlight
			const nodePath = nodePaths[0];
			const range = document.createRange();
			range.setStart(nodePath[0][0], nodePath[0][1]);
			range.setEnd(nodePath[1][0], nodePath[1][1]);

			const selectedText = range.extractContents();
			const hlblock = document.createElement("wpfts-highlight");
			hlblock.classList.add(classV);
			hlblock.appendChild(selectedText);
			range.insertNode(hlblock);

			window.scrollTo(0, hlblock.offsetTop);
		}
	}

	// @todo Words with special symbols (*, ?), phrases with extra words inside
	function highlightWords(words, classV = 'wpfts-highlight-word')
	{
		for (let word of words) {
			// Word can be a phrase
			islands = [];
			traverseSubNodes(mainNode, 0);	// Recollect nodes

			let sw = getWords(word);

			let nodePaths = findGoodNodes(sw, true, -1);
	
			// Loop in back order (to prevent overlaps)
			for (let ii = nodePaths.length - 1; ii >= 0; ii --) {
				let nodePath = nodePaths[ii];

				// Select and highlight
				const range = document.createRange();
				range.setStart(nodePath[0][0], nodePath[0][1]);
				range.setEnd(nodePath[1][0], nodePath[1][1]);
	
				const selectedText = range.extractContents();
				const hlblock = document.createElement("wpfts-highlight");
				hlblock.classList.add(classV);
				hlblock.appendChild(selectedText);
				range.insertNode(hlblock);
			}	
		}
	}

	function extractValueFromFragment(fragment, key) {
		const regex = new RegExp(`:\\$:${key}=([^&#]+)`);
		const match = fragment.match(regex);
		return match ? match[1] : null;
	}
	  
	function extractValuesFromFragment(fragment, key) {
		const regex = new RegExp(`:\\$:${key}=([^&#]+)`, 'g');
		const matches = fragment.matchAll(regex);
		return Array.from(matches).map(match => match[1]);
	}
	
	const urlFragment = window.location.hash.substring(1);
	const s1 = extractValueFromFragment(urlFragment, 'sentence');
	const sentence = decodeURIComponent(s1 ? s1 : '');
	const s2 = extractValueFromFragment(urlFragment, 'word');
	let w2 = decodeURIComponent(s2 ? s2 : '').split(',').map((v) => { return v.trim(); });
	let words = [];
	for (let w of w2) {
		let t = w.trim();
		if (t.length > 0) {
			words.push(t);
		}
	}

	mainNode = document.querySelector('body');

	if (sentence && (sentence.length > 0)) {
		islands = [];
		traverseSubNodes(mainNode, 0);
		
		//console.log('Smaller islands:');
		//console.log(islands);

		highlightSentence(sentence);
	}
  
	if (words && (words.length > 0)) {
		highlightWords(words);
	}
});
