// 单次注入抓取脚本：在浏览器页面上下文中执行，一次性返回结构化商品数据
(() => {
  // 1. 商品标题 (h1)
  const h1 = document.querySelector('h1');
  const title = (h1 ? h1.innerText : document.title).trim();

  // 2. 标题紧下方的简介条目 (intro: heading 与 body)
  const intro = [];
  const infoContainer = document.querySelector('.product__info-container, .product-info, [class*="product__info"], main');
  if (infoContainer) {
    const introBlock = infoContainer.querySelector('.rich-text-block, .product__description, [class*="highlights"], [class*="bullet"]');
    if (introBlock) {
      const ps = introBlock.querySelectorAll('p, li');
      ps.forEach(p => {
        const strongs = p.querySelectorAll('strong, b');
        if (strongs.length > 0) {
          strongs.forEach(s => {
            const heading = s.innerText.trim();
            if (heading) {
              const fullText = p.innerText;
              const idx = fullText.indexOf(heading);
              if (idx !== -1) {
                let body = fullText.slice(idx + heading.length).trim();
                body = body.replace(/^[:：\s-]+/, '');
                const nextMatch = body.search(/✅|✔|•|\n/);
                if (nextMatch !== -1) body = body.slice(0, nextMatch).trim();
                intro.push({ heading, body });
              }
            }
          });
        } else {
          const text = p.innerText.trim();
          if (text) intro.push({ heading: text, body: '' });
        }
      });
    }
  }

  // 3. 可见标签 (tags: 保留 emoji 与文字，排除隐藏 tag)
  const tags = [];
  const seenTags = new Set();
  const tagNodes = document.querySelectorAll('.product-feature-tag, .product-feature-tags span, [class*="feature-tag"], [class*="badge"]');
  tagNodes.forEach(node => {
    const text = node.innerText.trim();
    if (text && !seenTags.has(text) && node.offsetParent !== null) {
      seenTags.add(text);
      tags.push(text);
    }
  });

  // 4. 多件优惠档位 (quantity_discounts)
  const quantity_discounts = [];
  const qtyBreakNodes = document.querySelectorAll('.quantity-break, [class*="quantity-break"], [class*="volume-discount"], [class*="tier"]');
  qtyBreakNodes.forEach(node => {
    const text = node.innerText;
    const qtyMatch = text.match(/Buy\s*(\d+)/i) || text.match(/(\d+)\s*(?:件|pcs|pack)/i);
    if (qtyMatch) {
      const quantity = parseInt(qtyMatch[1], 10);
      const discountMatch = text.match(/Save\s*(\d+(?:\.\d+)?%)/i) || text.match(/(\d+(?:\.\d+)?%)\s*OFF/i);
      const entry = { quantity };
      if (discountMatch) entry.discount = discountMatch[1];
      quantity_discounts.push(entry);
    }
  });

  // 5. 轮播图/视频 (gallery: 高清去尺寸后缀，过滤空视频)
  const gallery = [];
  const seenGallery = new Set();
  const cleanMediaUrl = (raw) => {
    if (!raw) return null;
    let url = raw.trim();
    if (url.startsWith('//')) url = 'https:' + url;
    if (!url.startsWith('http')) return null;
    // 去除缩略图及尺寸限制参数 (如 _small, _100x100, &width=..., ?w=...)
    url = url.replace(/_(?:small|compact|medium|large|grande|\d+x\d+)/gi, '');
    url = url.replace(/([?&])width=\d+&?/gi, '$1');
    url = url.replace(/[?&]$/, '');
    return url;
  };

  const galleryItems = document.querySelectorAll('.product__media-list li, media-gallery [class*="media-item"], .slider--mobile [class*="slide"]');
  const targetNodes = galleryItems.length > 0 ? galleryItems : document.querySelectorAll('.product__media-list img, media-gallery img');

  targetNodes.forEach(item => {
    // 检查视频
    const video = item.querySelector ? item.querySelector('video') : null;
    if (video) {
      const vSrc = video.getAttribute('src') || (video.querySelector('source') ? video.querySelector('source').getAttribute('src') : null);
      const cleanV = cleanMediaUrl(vSrc);
      if (cleanV && !seenGallery.has(cleanV)) {
        seenGallery.add(cleanV);
        gallery.push(cleanV);
        return;
      }
    }
    // 检查图片
    const img = item.tagName === 'IMG' ? item : (item.querySelector ? item.querySelector('img') : null);
    if (img) {
      let src = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-original');
      const srcset = img.getAttribute('srcset');
      if (srcset) {
        const parts = srcset.split(',').map(s => s.trim().split(/\s+/));
        if (parts.length > 0) {
          const maxSrc = parts[parts.length - 1][0];
          if (maxSrc) src = maxSrc;
        }
      }
      const cleanImg = cleanMediaUrl(src);
      if (cleanImg && !seenGallery.has(cleanImg)) {
        seenGallery.add(cleanImg);
        gallery.push(cleanImg);
      }
    }
  });

  // 6. 详情描述容器 (details: 严格 DOM 顺序，仅有效媒体)
  const details = [];
  const descContainer = document.querySelector('.product__description, #product-description, [class*="description"], .rte');
  if (descContainer) {
    // 遍历直接或半直接语义块
    const blocks = descContainer.querySelectorAll('p, h1, h2, h3, h4, h5, h6, ul, ol, img, video');
    const processedNodes = new Set();

    blocks.forEach(node => {
      if (processedNodes.has(node)) return;

      // 图片处理 (包含 p > img)
      if (node.tagName === 'IMG' || (node.tagName === 'P' && node.querySelector('img'))) {
        const img = node.tagName === 'IMG' ? node : node.querySelector('img');
        processedNodes.add(img);
        if (node.tagName === 'P') processedNodes.add(node);
        const raw = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-original');
        const url = cleanMediaUrl(raw);
        if (url) {
          const isGif = url.toLowerCase().includes('.gif');
          details.push({ type: isGif ? 'gif' : 'image', url });
        }
        return;
      }

      // 视频处理 (仅保留真实有效 src)
      if (node.tagName === 'VIDEO' || (node.tagName === 'P' && node.querySelector('video'))) {
        const video = node.tagName === 'VIDEO' ? node : node.querySelector('video');
        processedNodes.add(video);
        if (node.tagName === 'P') processedNodes.add(node);
        const raw = video.getAttribute('src') || (video.querySelector('source') ? video.querySelector('source').getAttribute('src') : null);
        const url = cleanMediaUrl(raw);
        if (url) details.push({ type: 'video', url });
        return;
      }

      // 小标题处理
      if (/^H[1-6]$/.test(node.tagName)) {
        processedNodes.add(node);
        const text = node.innerText.trim();
        if (text) details.push({ type: 'heading', level: parseInt(node.tagName[1], 10), text });
        return;
      }

      // 列表处理
      if (node.tagName === 'UL' || node.tagName === 'OL') {
        processedNodes.add(node);
        const items = Array.from(node.querySelectorAll('li')).map(li => li.innerText.trim()).filter(Boolean);
        if (items.length > 0) details.push({ type: 'list', items, ordered: node.tagName === 'OL' });
        return;
      }

      // 普通段落文本
      if (node.tagName === 'P') {
        processedNodes.add(node);
        const text = node.innerText.trim();
        if (text) details.push({ type: 'text', text });
      }
    });
  }

  return {
    title,
    intro,
    tags,
    quantity_discounts,
    gallery,
    details
  };
})();
